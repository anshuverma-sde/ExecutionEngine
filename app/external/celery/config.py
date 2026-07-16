"""Celery-specific configuration."""
from app.core.config import settings

BROKER_URL: str = settings.CELERY_BROKER_URL
RESULT_BACKEND: str = settings.CELERY_RESULT_BACKEND

# Queue definitions
QUEUE_NOTIFICATIONS: str = "notifications"
QUEUE_RECONCILIATION: str = "reconciliation"
QUEUE_DEFAULT: str = "default"

# Task serialisation
TASK_SERIALIZER: str = "json"
RESULT_SERIALIZER: str = "json"
ACCEPT_CONTENT: list[str] = ["json"]
TIMEZONE: str = "Asia/Kolkata"
ENABLE_UTC: bool = True

# Beat schedule interval (seconds)
RECONCILIATION_INTERVAL_SECONDS: int = 60
