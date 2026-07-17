"""Celery Beat task: reconcile trades that never received a notification.

Runs every 60 seconds (configured in app/external/celery/app.py beat_schedule).

Logic:
  1. Query DB for trades where notification_sent=False AND notification_failed=False
     AND created_at < NOW()-2 minutes (grace period for in-flight Celery tasks).
  2. Re-enqueue send_trade_notification for each trade found.
  3. The Redis SETNX idempotency key in send_trade_notification deduplicates
     any tasks that are already queued or running — no double delivery.
  4. Log a summary: {unnotified_found, requeued, enqueue_failures}.

This task intentionally does NOT mark anything failed — that is done only
after max_retries are exhausted (notification_dead_letter).
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.external.celery.app import celery_app
from app.external.postgres.models import Trade
from app.external.postgres.sync_engine import get_sync_session

logger = logging.getLogger(__name__)

# Trades created within this window may still have in-flight Celery tasks
RECONCILIATION_GRACE_MINUTES = 2
# Maximum trades processed per reconciliation cycle (backpressure guard)
BATCH_LIMIT = 50


def _get_unnotified_trades_sync(grace_minutes: int = RECONCILIATION_GRACE_MINUTES, limit: int = BATCH_LIMIT):
    """Synchronous DB query for trades pending notification (Celery context)."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=grace_minutes)
    with get_sync_session() as session:
        result = session.execute(
            select(Trade)
            .where(Trade.notification_sent.is_(False))
            .where(Trade.notification_failed.is_(False))
            .where(Trade.created_at < cutoff)
            .order_by(Trade.created_at.asc())
            .limit(limit)
        )
        # Expunge to detach from session before returning
        trades = result.scalars().all()
        trade_ids = [str(t.id) for t in trades]
    return trade_ids


@celery_app.task(
    name="app.features.notifications.reconciliation.reconcile_notifications",
    queue="reconciliation",
)
def reconcile_notifications() -> dict:
    """Periodic task: re-enqueue any trades whose notifications were never sent.

    Runs every 60 seconds via Celery Beat (configured in celery/app.py).
    Idempotency is guaranteed by the Redis SETNX in send_trade_notification —
    double-enqueuing the same trade is safe and results in a single delivery.
    """
    from app.features.notifications.tasks import send_trade_notification

    logger.info("Reconciliation cycle started")

    trade_ids = _get_unnotified_trades_sync()
    unnotified_count = len(trade_ids)

    if not trade_ids:
        logger.info("Reconciliation: no unnotified trades found")
        return {"unnotified_found": 0, "requeued": 0, "enqueue_failures": 0}

    logger.info("Reconciliation: found %d unnotified trade(s)", unnotified_count)

    requeued = 0
    enqueue_failures = 0

    for trade_id in trade_ids:
        try:
            send_trade_notification.apply_async(args=[trade_id])
            requeued += 1
            logger.debug("Reconciliation: re-enqueued trade %s", trade_id)
        except Exception as exc:
            enqueue_failures += 1
            logger.error(
                "Reconciliation: failed to enqueue trade %s: %s", trade_id, exc
            )

    logger.info(
        "Reconciliation cycle complete | found=%d requeued=%d failures=%d",
        unnotified_count,
        requeued,
        enqueue_failures,
    )

    return {
        "unnotified_found": unnotified_count,
        "requeued": requeued,
        "enqueue_failures": enqueue_failures,
    }
