"""Celery queue depth metrics.

Queries Redis LLEN for each Celery queue to report task backlog.
A growing queue depth indicates workers can't keep up with enqueue rate.

SLA thresholds (configurable):
  notifications queue  > 100 tasks → WARN
  reconciliation queue > 10 tasks  → WARN
"""
import logging

logger = logging.getLogger(__name__)

NOTIFICATIONS_QUEUE_WARN = 100
RECONCILIATION_QUEUE_WARN = 10


def get_queue_depths() -> dict:
    """Return current task counts for each Celery queue.

    Uses a synchronous Redis connection (same broker URL as Celery).
    Safe to call from FastAPI async routes — redis-py is fast enough for a
    one-off INFO call and avoids the complexity of an async broker client.
    """
    from app.core.config import settings

    try:
        import redis as sync_redis
        r = sync_redis.from_url(settings.CELERY_BROKER_URL, decode_responses=True)

        # Celery stores tasks as LPUSH/BRPOP lists; queue name = list key
        notifications_depth = r.llen("notifications")
        reconciliation_depth = r.llen("reconciliation")
        default_depth = r.llen("celery")    # default queue for unrouted tasks

        r.close()

        return {
            "notifications": {
                "depth": notifications_depth,
                "warning_threshold": NOTIFICATIONS_QUEUE_WARN,
                "status": "warn" if notifications_depth > NOTIFICATIONS_QUEUE_WARN else "ok",
            },
            "reconciliation": {
                "depth": reconciliation_depth,
                "warning_threshold": RECONCILIATION_QUEUE_WARN,
                "status": "warn" if reconciliation_depth > RECONCILIATION_QUEUE_WARN else "ok",
            },
            "default": {
                "depth": default_depth,
                "status": "ok" if default_depth == 0 else "warn",
            },
        }

    except Exception as exc:
        logger.warning("Could not read Celery queue depths: %s", exc)
        return {"error": str(exc)}
