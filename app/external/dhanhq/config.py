"""DhanHQ-specific configuration."""
from app.core.config import settings

DHAN_CLIENT_ID: str = settings.DHAN_CLIENT_ID
DHAN_ACCESS_TOKEN: str = settings.DHAN_ACCESS_TOKEN

# Reconnect settings
MAX_RECONNECT_ATTEMPTS: int = 10
RECONNECT_BACKOFF_BASE: float = 1.5   # seconds
RECONNECT_BACKOFF_MAX: float = 60.0   # seconds
WATCHDOG_TIMEOUT_SECONDS: float = 30.0
