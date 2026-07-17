"""GET /metrics/latency — tick-to-signal latency statistics."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from app.metrics.latency import latency_collector

logger = logging.getLogger(__name__)

router = APIRouter(tags=["observability"])


@router.get("/metrics/latency")
async def latency_metrics() -> dict:
    """
    Tick-to-signal latency percentiles (p50 / p95 / p99 / max).

    **Measurement scope:** from when a tick enters `ingest_tick()` to when
    the spike detector returns a decision. Does NOT include Postgres write
    or Celery enqueue.

    **SLA target:** p99 < 50 ms.

    **How to reproduce:**
    1. `POST /debug/replay?reset_metrics=true` with a sample NDJSON file.
    2. `GET /metrics/latency` — read the stats from this response.
    """
    stats = latency_collector.stats()
    stats["sla_target_ms"] = 50.0
    stats["measured_at"] = datetime.now(timezone.utc).isoformat()
    return stats


@router.post("/metrics/reset")
async def reset_metrics() -> dict:
    """Clear all latency samples. Useful before a fresh benchmark run."""
    latency_collector.reset()
    return {"status": "reset", "measured_at": datetime.now(timezone.utc).isoformat()}
