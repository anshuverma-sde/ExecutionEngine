"""Celery Beat task: reconcile trades that never received a notification."""
import logging

from app.external.celery.app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.features.notifications.reconciliation.reconcile_notifications",
    queue="reconciliation",
)
def reconcile_notifications() -> dict:
    """
    Periodic task that finds trades with notification_sent=False and
    re-queues them for delivery.

    Runs every 60 seconds via Celery Beat.
    """
    pass
