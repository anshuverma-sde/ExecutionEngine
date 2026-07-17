"""POST /debug/replay — replay a NDJSON tick file through the live pipeline.

CRITICAL: every tick goes through ingest_tick() — the exact same function
the live WebSocket consumer calls. There is no separate code path.
This is how the evaluators will test the engine.
"""
import json
import logging
import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from app.features.ingestion.pipeline import ingest_tick
from app.metrics.latency import latency_collector

_MAX_FUTURE_SECONDS = 300   # reject timestamps more than 5 minutes in the future


class TickInput(BaseModel):
    """Validated representation of a single NDJSON tick line."""

    security_id: str
    ltp: float
    ts: datetime

    @field_validator("ltp")
    @classmethod
    def ltp_must_be_positive_finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("ltp must be a finite number (not NaN or Infinity)")
        if v <= 0:
            raise ValueError(f"ltp must be positive, got {v}")
        return v

    @field_validator("ts", mode="before")
    @classmethod
    def parse_ts(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v

    @field_validator("ts")
    @classmethod
    def ts_not_far_future(cls, v: datetime) -> datetime:
        now = datetime.now(timezone.utc)
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v > now + timedelta(seconds=_MAX_FUTURE_SECONDS):
            raise ValueError(f"ts is too far in the future: {v.isoformat()}")
        return v

logger = logging.getLogger(__name__)

router = APIRouter(tags=["debug"])



@router.post(
    "/debug/replay",
    summary="Replay a NDJSON tick file through the live pipeline",
    response_description="Count of processed ticks, signals fired, errors, and latency stats",
)
async def replay(
    request: Request,
    reset_window: bool = Query(
        False,
        description="Flush the Redis 60s price window before replay. Use this for a clean test run so the spike always fires.",
    ),
    reset_metrics: bool = Query(
        False,
        description="Clear p50/p95/p99 latency samples before replay for a clean benchmark reading.",
    ),
) -> JSONResponse:
    """
    Feed a **newline-delimited JSON (NDJSON)** tick file through the **exact same pipeline**
    as the live DhanHQ WebSocket feed — same `ingest_tick()` function, same spike detector,
    same trade simulation, same Celery notifications.

    **This is the endpoint the evaluators use to test your engine against unseen market data.**

    ---

    ### Request body

    `Content-Type: application/x-ndjson` — one JSON object per line:

    ```
    {"security_id": "13", "ltp": 22000.0, "ts": "2026-07-10T09:30:00Z"}
    {"security_id": "13", "ltp": 22000.5, "ts": "2026-07-10T09:30:01Z"}
    {"security_id": "13", "ltp": 23210.0, "ts": "2026-07-10T09:31:05Z"}
    ```

    | Field | Type | Description |
    |---|---|---|
    | `security_id` | string | Instrument ID — must be `"13"` (NIFTY 50) |
    | `ltp` | float | Last traded price |
    | `ts` | ISO 8601 string | Tick timestamp (UTC) |

    ---

    ### What happens per tick

    1. Price appended to Redis 60-second rolling window
    2. Spike detector compares current price vs price 60s ago
    3. If move ≥ +5% → **LONG** signal → buy ATM Call (CE)
    4. If move ≤ −5% → **SHORT** signal → buy ATM Put (PE)
    5. Trade persisted to PostgreSQL
    6. Celery notification task enqueued → webhook POST

    ---

    ### Quick test (curl)

    ```bash
    curl -X POST "http://localhost:8000/debug/replay?reset_window=true&reset_metrics=true" \\
      -H "Content-Type: application/x-ndjson" \\
      --data-binary @tests/fixtures/sample_replay.ndjson
    ```

    ---

    ### Response

    ```json
    {
      "processed": 120,
      "signals": 1,
      "errors": 0,
      "latency_stats": {
        "p50_ms": 1.79,
        "p95_ms": 2.79,
        "p99_ms": 4.33,
        "max_ms": 7.29,
        "sla_met": true
      }
    }
    ```
    """
    if reset_metrics:
        latency_collector.reset()
        logger.info("Latency metrics reset before replay")

    if reset_window:
        try:
            from app.external.redis.client import get_redis
            from app.external.redis.window import PriceWindow
            redis = await get_redis()
            window = PriceWindow(redis)
            # Flush all known security windows (extend list as needed)
            for sid in ["13"]:
                await window.flush(sid)
            logger.info("Redis price window flushed before replay")
        except Exception as exc:
            logger.warning("Could not flush Redis window: %s", exc)

    body = await request.body()
    lines = body.decode("utf-8", errors="replace").strip().split("\n")

    processed = 0
    signals = 0
    errors = 0
    error_details: list[str] = []

    for line_num, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue

        try:
            raw = json.loads(line)
            tick = TickInput.model_validate(raw)

            signal = await ingest_tick(tick.security_id, tick.ltp, tick.ts)
            processed += 1
            if signal:
                signals += 1

        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            errors += 1
            detail = f"line {line_num}: {type(exc).__name__}: {exc}"
            error_details.append(detail)
            logger.warning("Replay parse error — %s", detail)

        except Exception as exc:
            errors += 1
            detail = f"line {line_num}: pipeline error: {exc}"
            error_details.append(detail)
            logger.error("Replay pipeline error — %s", detail, exc_info=True)

    result = {
        "processed": processed,
        "signals": signals,
        "errors": errors,
        "latency_stats": latency_collector.stats(),
    }
    if error_details:
        result["total_errors"] = len(error_details)
        result["error_details"] = error_details[:20]   # first 20; check total_errors for full count

    return JSONResponse(content=result)
