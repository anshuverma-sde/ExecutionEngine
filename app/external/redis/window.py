"""Redis ZSET-based rolling price window for spike detection."""
import logging
import time

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60
WINDOW_KEY_PREFIX = "price_window:"


class PriceWindow:
    """Maintains a 60-second rolling window of price ticks per symbol using Redis ZSETs."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    def _key(self, symbol: str) -> str:
        return f"{WINDOW_KEY_PREFIX}{symbol}"

    async def add(self, symbol: str, price: float, timestamp: float | None = None) -> None:
        """Add a price tick to the rolling window."""
        pass

    async def get_window(self, symbol: str) -> list[float]:
        """Return all prices in the current 60-second window for the given symbol."""
        pass

    async def get_baseline(self, symbol: str) -> float | None:
        """Return the mean price over the rolling window, or None if insufficient data."""
        pass

    async def prune(self, symbol: str) -> None:
        """Remove ticks older than WINDOW_SECONDS from the window."""
        pass
