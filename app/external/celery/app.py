"""Celery application instance, configuration and Beat schedule."""
import logging

from celery import Celery

from app.external.celery import config as celery_config

logger = logging.getLogger(__name__)

celery_app = Celery(
    "execution_engine",
    broker=celery_config.BROKER_URL,
    backend=celery_config.RESULT_BACKEND,
    include=[
        "app.features.notifications.tasks",
        "app.features.notifications.reconciliation",
    ],
)

celery_app.conf.update(
    task_serializer=celery_config.TASK_SERIALIZER,
    result_serializer=celery_config.RESULT_SERIALIZER,
    accept_content=celery_config.ACCEPT_CONTENT,
    timezone=celery_config.TIMEZONE,
    enable_utc=celery_config.ENABLE_UTC,
    task_track_started=True,
    # Reliability settings — critical for at-least-once delivery
    task_acks_late=True,              # Only ACK after task completes (not on pickup)
    task_reject_on_worker_lost=True,  # Requeue if worker process dies mid-task
    worker_prefetch_multiplier=1,     # Fair dispatch — one task at a time per worker
    task_routes={
        "app.features.notifications.tasks.*": {"queue": celery_config.QUEUE_NOTIFICATIONS},
        "app.features.notifications.reconciliation.*": {"queue": celery_config.QUEUE_RECONCILIATION},
    },
    beat_schedule={
        "reconcile-notifications": {
            "task": "app.features.notifications.reconciliation.reconcile_notifications",
            "schedule": celery_config.RECONCILIATION_INTERVAL_SECONDS,
            "options": {"queue": celery_config.QUEUE_RECONCILIATION},
        },
    },
)
