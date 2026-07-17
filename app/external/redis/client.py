"""Async Redis connection pool management."""
import logging

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_redis_client: aioredis.Redis | None = None


async def init_redis(redis_url: str) -> aioredis.Redis:
    """Create and return the shared async Redis client."""
    global _redis_client
    _redis_client = aioredis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=100,  # supports ~10x tick rate before pool exhaustion
    )
    # Verify connectivity
    await _redis_client.ping()
    logger.info("Redis client initialised")
    return _redis_client


async def get_redis() -> aioredis.Redis:
    """Return the active Redis client, raising if not initialised."""
    if _redis_client is None:
        raise RuntimeError("Redis client has not been initialised — call init_redis() first")
    return _redis_client


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis client closed")
