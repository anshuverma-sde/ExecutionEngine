# TICKET-003: Redis Rolling 60-Second Price Window

**Branch:** `feature/TICKET-003-redis-rolling-window`  
**Priority:** P0 — Required before TICKET-005 (spike detection)  
**Estimate:** ~1.5h

## Summary
Implement the Redis-backed rolling price window that maintains 60 seconds of tick history per instrument. This is the data structure that the spike detector reads on every tick. Choice and justification: **Sorted Set** (ZSET).

## Design Decision: Redis Sorted Sets

**Why Sorted Set over Streams or Lists:**
- Score = Unix timestamp (milliseconds) → O(log N) range queries by time
- `ZRANGEBYSCORE key (t-60) +inf LIMIT 0 1` retrieves oldest tick in window in one command
- `ZREMRANGEBYSCORE key -inf (t-60)` expires old ticks atomically
- No additional consumer group management (Streams would over-engineer this use case)
- Lists require O(N) scan to find t-60 boundary

**Key schema:** `price_window:{security_id}` e.g. `price_window:13`  
**Value:** JSON string `{"ltp": 22450.5, "ts": "2026-07-10T09:31:04.221Z"}`  
**Score:** Unix timestamp in milliseconds (float)

## Scope

### Files to Create
- `app/external/redis/client.py` — async Redis client (aioredis/redis-py async)
- `app/external/redis/window.py` — PriceWindow class with these methods:
  - `async append(security_id, ltp, ts)` — ZADD + ZREMRANGEBYSCORE (atomic via pipeline)
  - `async get_price_at_t_minus_60(security_id, now_ts)` — ZRANGEBYSCORE for oldest in window
  - `async get_current_price(security_id)` — ZRANGE with BYSCORE, latest entry
  - `async window_size(security_id)` — ZCARD for monitoring

### Redis Operations Pattern
```python
async def append(self, security_id: str, ltp: float, ts: datetime):
    now_ms = ts.timestamp() * 1000
    cutoff_ms = now_ms - 60_000
    key = f"price_window:{security_id}"
    async with self.redis.pipeline(transaction=True) as pipe:
        pipe.zadd(key, {json.dumps({"ltp": ltp, "ts": ts.isoformat()}): now_ms})
        pipe.zremrangebyscore(key, "-inf", cutoff_ms)
        await pipe.execute()

async def get_price_at_t_minus_60(self, security_id: str, now_ts: datetime) -> float | None:
    now_ms = now_ts.timestamp() * 1000
    cutoff_ms = now_ms - 60_000
    key = f"price_window:{security_id}"
    # Get first entry at or after cutoff (oldest in 60s window)
    results = await self.redis.zrangebyscore(key, cutoff_ms, "+inf", start=0, num=1, withscores=False)
    if results:
        return json.loads(results[0])["ltp"]
    return None
```

## Acceptance Criteria
- [ ] `append()` atomically adds tick and purges expired entries
- [ ] `get_price_at_t_minus_60()` returns correct price when window has >= 60s of data
- [ ] `get_price_at_t_minus_60()` returns `None` when window has < 60s of data (cold start)
- [ ] Operations complete in < 2ms under normal conditions
- [ ] Key TTL set to 120s as safety net (auto-cleanup if process dies)

## Dependencies
- TICKET-001 (Redis service in docker-compose)

## Notes
- Cold start: first 60 seconds of uptime will return None from `get_price_at_t_minus_60` — spike detector must handle this gracefully (no signal emitted)
- Use `redis-py >= 5.0` with async support (no separate `aioredis` needed)
- Pipeline the ZADD + ZREMRANGEBYSCORE to minimize round-trips
