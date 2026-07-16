# Plan: TICKET-003 — Redis Rolling 60-Second Price Window

## Branch
```bash
git checkout -b feature/TICKET-003-redis-rolling-window
```

## Implementation Steps

### Step 1 — `app/external/redis/client.py`
```python
import redis.asyncio as aioredis
from app.core.config import settings

_redis_pool: aioredis.Redis | None = None

async def get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_pool

async def close_redis():
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None
```

### Step 2 — `app/external/redis/window.py`
```python
import json
from datetime import datetime
import redis.asyncio as aioredis

WINDOW_SECONDS = 60
KEY_TTL_SECONDS = 120  # safety net TTL on the key

class PriceWindow:
    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    def _key(self, security_id: str) -> str:
        return f"price_window:{security_id}"

    async def append(self, security_id: str, ltp: float, ts: datetime) -> None:
        """Add tick and evict entries older than WINDOW_SECONDS."""
        now_ms = ts.timestamp() * 1000
        cutoff_ms = now_ms - (WINDOW_SECONDS * 1000)
        key = self._key(security_id)
        value = json.dumps({"ltp": ltp, "ts": ts.isoformat()})

        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.zadd(key, {value: now_ms})
            pipe.zremrangebyscore(key, "-inf", cutoff_ms)
            pipe.expire(key, KEY_TTL_SECONDS)
            await pipe.execute()

    async def get_price_at_t_minus_60(
        self, security_id: str, now_ts: datetime
    ) -> float | None:
        """
        Return the oldest price in the 60s window (approximates P(t-60)).
        Returns None if window has < 60s of data.
        """
        now_ms = now_ts.timestamp() * 1000
        cutoff_ms = now_ms - (WINDOW_SECONDS * 1000)
        key = self._key(security_id)

        results = await self.redis.zrangebyscore(
            key, cutoff_ms, "+inf", start=0, num=1
        )
        if not results:
            return None
        return json.loads(results[0])["ltp"]

    async def get_latest_price(self, security_id: str) -> float | None:
        """Return most recent price in window."""
        key = self._key(security_id)
        results = await self.redis.zrange(key, -1, -1)
        if not results:
            return None
        return json.loads(results[0])["ltp"]

    async def window_size(self, security_id: str) -> int:
        return await self.redis.zcard(self._key(security_id))

    async def flush(self, security_id: str) -> None:
        """Remove all entries for an instrument (used for replay reset)."""
        await self.redis.delete(self._key(security_id))
```

### Step 3 — Integrate into Lifespan
In `app/main.py`:
```python
from app.external.redis.client import get_redis, close_redis
from app.external.redis.window import PriceWindow

@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = await get_redis()
    app.state.price_window = PriceWindow(redis)
    yield
    await close_redis()
```

### Step 4 — Singleton Access Pattern
```python
# app/external/redis/window.py — module-level singleton
_price_window: PriceWindow | None = None

def get_price_window(app=None) -> PriceWindow:
    # accessed via app.state or module singleton
    return _price_window
```

## Unit Tests (Verify Manually)
```python
# Quick smoke test script
import asyncio
from datetime import datetime, timedelta
from app.external.redis.client import get_redis
from app.external.redis.window import PriceWindow

async def test():
    redis = await get_redis()
    window = PriceWindow(redis)
    
    base = datetime(2026, 7, 10, 9, 30, 0)
    
    # Add 61 seconds of ticks
    for i in range(62):
        ts = base + timedelta(seconds=i)
        await window.append("13", 22000 + i, ts)
    
    # At t=61s, t-60 should return price at t=1s (22001)
    t_now = base + timedelta(seconds=61)
    p_t60 = await window.get_price_at_t_minus_60("13", t_now)
    print(f"P(t-60) = {p_t60}")  # Should be ~22001
    
    size = await window.window_size("13")
    print(f"Window size = {size}")  # Should be ~61 entries

asyncio.run(test())
```

## Verification
- `window_size()` never exceeds ~60 * tick_rate entries
- `get_price_at_t_minus_60()` returns `None` when < 60s of data
- Pipeline ZADD+ZREMRANGEBYSCORE is atomic

## Commit Message
```
feat: implement Redis Sorted Set rolling 60s price window
```
