"""Webhook outbound notification configuration."""
from app.core.config import settings

WEBHOOK_URL: str = settings.WEBHOOK_URL
WEBHOOK_TIMEOUT_SECONDS: int = settings.WEBHOOK_TIMEOUT_SECONDS

# Retry settings
MAX_RETRIES: int = 3
RETRY_BACKOFF_BASE: float = 2.0  # seconds
