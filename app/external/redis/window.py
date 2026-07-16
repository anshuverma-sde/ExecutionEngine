"""Redis Sorted Set-based rolling 60-second price window.

Design choice: Sorted Sets (ZSET)
- Score = Unix timestamp in milliseconds → O(log N) range queries by time
- ZRANGEBYSCORE fetches oldest tick in window in one command
- ZREMRANGEBYSCORE expires old entries atomically in a pipeline
- No consumer group management overhead (Streams would over-engineer this)
- Lists require O(N) scan to find the t-60 boundary
"""
import json
import logging
from datetime import datetime

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60
KEY_PREFIX = "price_window:"
KEY_TTL_SECONDS = 120  # safety-net TTL — auto-cleanup if process dies


class PriceWindow:
    """Maintains a 60-second rolling window of LTP ticks per security using Redis ZSETs.

    Key schema : price_window:{security_id}
    Value      : JSON string {"ltp": 22450.5, "ts": "<iso>"}
    Score      : Unix timestamp in milliseconds (float)
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    def _key(self, security_id: str) -> str:
        return f"{KEY_PREFIX}{security_id}"

    async def append(self, security_id: str, ltp: float, ts: datetime) -> None:
        """Add a tick and atomically evict entries older than 60 seconds.

        Uses a pipeline to keep ZADD + ZREMRANGEBYSCORE + EXPIRE as a single
        round-trip. Not a Lua transaction — pipeline is sufficient because the
        eviction boundary only moves forward in time.
        """
        now_ms = ts.timestamp() * 1000
        cutoff_ms = now_ms - (WINDOW_SECONDS * 1000)
        key = self._key(security_id)
        value = json.dumps({"ltp": ltp, "ts": ts.isoformat()})

        async with self._redis.pipeline(transaction=False) as pipe:
            pipe.zadd(key, {value: now_ms})
            pipe.zremrangebyscore(key, "-inf", cutoff_ms)
            pipe.expire(key, KEY_TTL_SECONDS)
            await pipe.execute()

    async def get_price_at_t_minus_60(
        self, security_id: str, now_ts: datetime
    ) -> float | None:
        """Return the oldest price in the 60-second window (approximates P(t-60)).

        Returns None when the window has less than 60 seconds of history
        (cold-start condition — no signal should be emitted).
        """
        now_ms = now_ts.timestamp() * 1000
        cutoff_ms = now_ms - (WINDOW_SECONDS * 1000)
        key = self._key(security_id)

        # Fetch the first entry AT OR AFTER the 60s boundary
        results = await self._redis.zrangebyscore(
            key, cutoff_ms, "+inf", start=0, num=1
        )
        if not results:
            return None

        try:
            return float(json.loads(results[0])["ltp"])
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Corrupt window entry for %s: %s", security_id, exc)
            return None

    async def get_latest_price(self, security_id: str) -> float | None:
        """Return the most recent price in the window."""
        key = self._key(security_id)
        results = await self._redis.zrange(key, -1, -1)
        if not results:
            return None
        try:
            return float(json.loads(results[0])["ltp"])
        except (KeyError, ValueError, json.JSONDecodeError):
            return None

    async def window_size(self, security_id: str) -> int:
        """Return the number of ticks currently in the window."""
        return await self._redis.zcard(self._key(security_id))

    async def flush(self, security_id: str) -> None:
        """Delete all entries for a security (used before replay runs)."""
        await self._redis.delete(self._key(security_id))
        logger.info("Price window flushed for security_id=%s", security_id)
