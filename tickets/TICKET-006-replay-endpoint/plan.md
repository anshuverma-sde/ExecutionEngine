# Plan: TICKET-006 — Replay Endpoint

## Branch
```bash
git checkout -b feature/TICKET-006-replay-endpoint
```

## Implementation Steps

### Step 1 — `app/api/routes/debug.py`
```python
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse

from app.features.ingestion.pipeline import ingest_tick
from app.metrics.latency import latency_collector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/debug", tags=["debug"])


@router.post("/replay")
async def replay(
    request: Request,
    reset_window: bool = Query(False, description="Flush Redis window before replay"),
    reset_metrics: bool = Query(False, description="Reset latency metrics before replay"),
):
    """
    Replay a newline-delimited JSON tick file through the live pipeline.
    Each line: {"security_id": "13", "ltp": 22450.5, "ts": "2026-07-10T09:31:04.221Z"}
    """
    if reset_metrics:
        latency_collector.reset()

    if reset_window:
        from app.external.redis.window import PriceWindow
        from app.external.redis.client import get_redis
        redis = await get_redis()
        window = PriceWindow(redis)
        await window.flush("13")
        logger.info("Redis price window flushed for replay")

    body = await request.body()
    lines = body.decode("utf-8", errors="replace").strip().split("\n")

    results = {"processed": 0, "errors": 0, "signals": 0, "error_details": []}

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            tick = json.loads(line)
            security_id = str(tick["security_id"])
            ltp = float(tick["ltp"])
            ts_str = tick["ts"]
            # Handle both UTC 'Z' suffix and '+00:00'
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

            signal = await ingest_tick(security_id, ltp, ts)
            results["processed"] += 1
            if signal:
                results["signals"] += 1

        except (KeyError, ValueError, json.JSONDecodeError) as e:
            results["errors"] += 1
            detail = f"Line {line_num}: {type(e).__name__}: {e}"
            results["error_details"].append(detail)
            logger.warning(f"Replay parse error — {detail}")
        except Exception as e:
            results["errors"] += 1
            logger.error(f"Replay pipeline error on line {line_num}: {e}")

    # Attach latency stats after processing
    results["latency_stats"] = latency_collector.stats()

    return JSONResponse(content=results)
```

### Step 2 — Register Router in `app/api/router.py`
```python
from app.api.routes import health, debug, metrics, ai

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(debug.router)
api_router.include_router(metrics.router)
api_router.include_router(ai.router)
```

### Step 3 — Sample Replay File
Create `tests/sample_replay.ndjson`:
```jsonl
{"security_id": "13", "ltp": 22000.0, "ts": "2026-07-10T09:30:00.000Z"}
{"security_id": "13", "ltp": 22001.0, "ts": "2026-07-10T09:30:01.000Z"}
... (60 ticks at 22000 to fill window)
{"security_id": "13", "ltp": 23100.5, "ts": "2026-07-10T09:31:01.000Z"}
```
The last tick is +5% above the 60s-ago reference → triggers LONG signal.

### Step 4 — Replay Test Script
```bash
# Create a replay file that should produce at least 1 signal
python scripts/generate_replay.py > /tmp/replay.ndjson

# Run replay
curl -X POST http://localhost:8000/debug/replay \
  --data-binary @/tmp/replay.ndjson \
  -H "Content-Type: text/plain" \
  ?reset_window=true&reset_metrics=true

# Expected response:
# {
#   "processed": 62,
#   "errors": 0,
#   "signals": 1,
#   "latency_stats": {"p50_ms": 0.85, "p95_ms": 1.2, "p99_ms": 2.1, "max_ms": 4.8, "count": 62}
# }
```

### Step 5 — `scripts/generate_replay.py`
```python
#!/usr/bin/env python3
"""Generate a replay NDJSON file that triggers a LONG signal."""
import json
from datetime import datetime, timedelta, timezone

base = datetime(2026, 7, 10, 9, 30, 0, tzinfo=timezone.utc)
base_price = 22000.0

# 61 ticks at base_price (fills 60s window)
for i in range(61):
    ts = base + timedelta(seconds=i)
    print(json.dumps({"security_id": "13", "ltp": base_price + i * 0.1, "ts": ts.isoformat().replace("+00:00", "Z")}))

# Spike tick: +5.5% above tick at t=0
spike_ts = base + timedelta(seconds=62)
spike_price = round(base_price * 1.055, 2)
print(json.dumps({"security_id": "13", "ltp": spike_price, "ts": spike_ts.isoformat().replace("+00:00", "Z")}))
```

## Verification Checklist
- [ ] `POST /debug/replay` with valid NDJSON returns `{"processed": N, "signals": 1}`
- [ ] Malformed line in file → `errors` incremented, processing continues
- [ ] `?reset_window=true` flushes Redis before replay (fresh state)
- [ ] `?reset_metrics=true` clears latency samples
- [ ] Timestamps from replay file are used for window scoring (not `datetime.now()`)
- [ ] Same `ingest_tick()` function called (verified by grepping for other paths)

## Commit Message
```
feat: add /debug/replay endpoint routing through shared ingestion pipeline
```
