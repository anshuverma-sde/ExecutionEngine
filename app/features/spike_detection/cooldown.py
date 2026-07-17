"""Redis-backed per-security cooldown to prevent signal storms.

Design decision (documented in README):
  Without a cooldown, a sustained 5%+ move generates a signal on EVERY tick
  — potentially thousands of trades per minute on a busy feed. A 60-second
  cooldown matches the detection window and limits to at most one signal per
  instrument per minute.

  Redis SETNX (SET with NX flag) provides atomic check-and-set — no race
  condition between checking and setting the cooldown key.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

COOLDOWN_KEY_PREFIX = "cooldown:"
COOLDOWN_SECONDS = 60   # matches the 60s detection window


class CooldownManager:
    """Prevents duplicate spike signals within the cooldown window.

    Uses Redis SET NX + EX: atomic, no separate check-then-set race.
    """

    def __init__(self, redis_client: Any, cooldown_seconds: int = COOLDOWN_SECONDS) -> None:
        self._redis = redis_client
        self.cooldown_seconds = cooldown_seconds

    def _key(self, security_id: str) -> str:
        return f"{COOLDOWN_KEY_PREFIX}{security_id}"

    async def is_cooled_down(self, security_id: str) -> bool:
        """Return True if security is in cooldown (signal should be suppressed)."""
        return await self._redis.exists(self._key(security_id)) == 1

    async def set_cooldown(self, security_id: str) -> bool:
        """Atomically claim the cooldown slot.

        Returns True if the cooldown was set (signal is new),
        False if cooldown was already active (duplicate — suppress).
        """
        result = await self._redis.set(
            self._key(security_id),
            "1",
            nx=True,            # only set if key does NOT exist
            ex=self.cooldown_seconds,
        )
        return result is not None   # None → key existed → duplicate

    async def clear_cooldown(self, security_id: str) -> None:
        """Manually clear the cooldown (useful for tests and replay resets)."""
        await self._redis.delete(self._key(security_id))
        logger.debug("Cooldown cleared for security_id=%s", security_id)
