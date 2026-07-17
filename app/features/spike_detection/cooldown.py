"""Redis-backed per-symbol cooldown to prevent duplicate signals."""
import logging
from typing import Any

logger = logging.getLogger(__name__)

COOLDOWN_KEY_PREFIX = "cooldown:"
DEFAULT_COOLDOWN_SECONDS: int = 30


class CooldownManager:
    """
    Prevents multiple spike signals for the same symbol within a cooldown window.

    Uses Redis SET with an expiry to track active cooldowns.
    """

    def __init__(self, redis_client: Any, cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS) -> None:
        self._redis = redis_client
        self.cooldown_seconds = cooldown_seconds

    def _key(self, symbol: str) -> str:
        return f"{COOLDOWN_KEY_PREFIX}{symbol}"

    async def is_cooled_down(self, symbol: str) -> bool:
        """Return True if the symbol is still in cooldown (signal should be suppressed)."""
        pass

    async def set_cooldown(self, symbol: str) -> None:
        """Mark the symbol as active and start the cooldown timer."""
        pass

    async def clear_cooldown(self, symbol: str) -> None:
        """Manually clear the cooldown for a symbol (e.g. for testing)."""
        pass
