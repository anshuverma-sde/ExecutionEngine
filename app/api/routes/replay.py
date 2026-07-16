"""POST /debug/replay — replay a NDJSON tick file through the live pipeline.

CRITICAL: every tick goes through ingest_tick() — the exact same function
the live WebSocket consumer calls. There is no separate code path.
This is how the evaluators will test the engine.
"""
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.features.ingestion.pipeline import ingest_tick
from app.metrics.latency import latency_collector

logger = logging.getLogger(__name__)

router = APIRouter(tags=["debug"])


@router.post("/debug/replay")
async def replay(
    request: Request,
    reset_window: bool = Query(
        False,
        description="Flush the Redis price window before processing (clean slate).",
    ),
    reset_metrics: bool = Query(
        False,
        description="Clear latency samples before processing.",
    ),
) -> JSONResponse:
    """
    Replay a newline-delimited JSON tick file through the live ingestion pipeline.

    Each line must be:
        {"security_id": "13", "ltp": 22450.5, "ts": "2026-07-10T09:31:04.221Z"}

    The ticks are fed through ingest_tick() — identical to the live WebSocket path.
    Spike detection, trade simulation, and Celery notifications all fire normally.

    Query params:
    - **reset_window**: flush Redis price window before replay (recommended for clean test runs)
    - **reset_metrics**: clear latency samples before replay
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
            tick = json.loads(line)
            security_id = str(tick["security_id"])
            ltp = float(tick["ltp"])
            # Accept both "Z" suffix and "+00:00"
            ts_raw: str = tick["ts"]
            ts: datetime = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))

            signal = await ingest_tick(security_id, ltp, ts)
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
        result["error_details"] = error_details[:20]   # cap to avoid huge responses

    return JSONResponse(content=result)
