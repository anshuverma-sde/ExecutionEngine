"""
Tick ingestion pipeline — THE single entry point for all market data.

Both the live DhanHQ WebSocket consumer and the POST /debug/replay endpoint
call ingest_tick(). There is no separate code path.

Call init_pipeline() once during application startup, then call ingest_tick()
for every incoming price tick.
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Callable, Awaitable

from app.metrics.latency import latency_collector

logger = logging.getLogger(__name__)

# Module-level dependencies — injected at startup via init_pipeline()
_price_window: Any | None = None
_spike_detector: Any | None = None
_handle_signal: Callable[..., Awaitable[None]] | None = None
_session_factory: Any | None = None


def init_pipeline(
    price_window: Any,
    spike_detector: Any,
    handle_signal: Callable[..., Awaitable[None]],
    session_factory: Any,
) -> None:
    """Wire up pipeline dependencies. Must be called before ingest_tick()."""
    global _price_window, _spike_detector, _handle_signal, _session_factory
    _price_window = price_window
    _spike_detector = spike_detector
    _handle_signal = handle_signal
    _session_factory = session_factory
    logger.info("Ingestion pipeline initialised")


async def ingest_tick(security_id: str, ltp: float, ts: datetime):
    """
    Process a single price tick through the full detection pipeline.

    Latency measurement scope (TICKET-011):
      t_start  → Redis window append
               → Redis fetch P(t-60)
               → Spike threshold computation
      t_end    ← signal decision returned

    NOT included in measurement: Postgres write, Celery enqueue.

    Returns the Signal if one was emitted, else None.
    """
    if _price_window is None or _spike_detector is None:
        logger.warning("Pipeline not initialised — dropping tick %s@%.2f", security_id, ltp)
        return None

    t_start = time.perf_counter()
    signal = None

    try:
        # 1. Append to Redis rolling window (ZADD + ZREMRANGEBYSCORE pipeline)
        await _price_window.append(security_id, ltp, ts)

        # 2. Run spike detector (reads P(t-60) from Redis, computes return)
        signal = await _spike_detector.detect(security_id, ltp, ts)

    except Exception as exc:
        logger.error(
            "Pipeline error for tick %s@%.2f: %s", security_id, ltp, exc, exc_info=True
        )
        return None
    finally:
        # Always record latency — even on error paths
        latency_ms = (time.perf_counter() - t_start) * 1000
        latency_collector.record(latency_ms)

    # 3. If a signal was detected, dispatch trade simulation in background.
    #    asyncio.create_task() returns immediately — does NOT block the pipeline.
    if signal and _handle_signal and _session_factory:
        asyncio.create_task(_dispatch_signal(signal))

    return signal


async def _dispatch_signal(signal) -> None:
    """Run handle_signal() in a background task so the pipeline is non-blocking."""
    try:
        async with _session_factory() as db:
            await _handle_signal(signal, db)
    except Exception as exc:
        logger.error("Signal dispatch failed: %s", exc, exc_info=True)
