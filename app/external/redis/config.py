"""Redis-specific configuration extracted from core settings."""
from app.core.config import settings

REDIS_URL: str = settings.REDIS_URL
CELERY_BROKER_URL: str = settings.CELERY_BROKER_URL
CELERY_RESULT_BACKEND: str = settings.CELERY_RESULT_BACKEND

# DB index assignments (documented here for clarity)
PRICE_WINDOW_DB: int = 0   # Same DB as general cache
COOLDOWN_DB: int = 0       # Cooldown keys share DB 0 with price window
