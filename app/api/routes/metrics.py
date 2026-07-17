"""GET /metrics/latency — tick-to-signal latency statistics.
GET /reconciliation/status — Celery Beat reconciliation health check.
"""
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


@router.get("/reconciliation/status")
async def reconciliation_status() -> dict:
    """Return the count of trades pending reconciliation (unnotified + not permanently failed).

    Queries live DB state. Useful for confirming the Beat task is making progress.
    """
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session
    from datetime import timedelta

    from app.core.config import settings
    from app.external.postgres.models import Trade

    sync_url = settings.sync_database_url
    engine = create_engine(sync_url, pool_size=2, pool_pre_ping=True)

    grace_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=2)

    with Session(engine) as session:
        pending = session.execute(
            select(func.count(Trade.id))
            .where(Trade.notification_sent.is_(False))
            .where(Trade.notification_failed.is_(False))
            .where(Trade.created_at < grace_cutoff)
        ).scalar_one()

        failed = session.execute(
            select(func.count(Trade.id))
            .where(Trade.notification_failed.is_(True))
        ).scalar_one()

    return {
        "pending_reconciliation": pending,
        "permanently_failed": failed,
        "measured_at": datetime.now(timezone.utc).isoformat(),
    }
