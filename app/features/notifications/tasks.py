"""Celery tasks for sending trade notifications."""
import logging

from app.external.celery.app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.features.notifications.tasks.send_trade_notification",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    queue="notifications",
)
def send_trade_notification(self, trade_id: str) -> dict:
    """
    Send a webhook notification for the given trade ID.

    Retries up to 3 times with a 5-second delay on failure.
    """
    pass
