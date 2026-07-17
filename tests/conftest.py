"""Shared pytest fixtures for the Instant Strike test suite."""
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── event loop ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── In-memory Redis fake ──────────────────────────────────────────────────────

class FakeRedis:
    """In-memory Redis substitute covering ZSETs, strings, SET NX, pipeline."""

    def __init__(self):
        self._zsets: dict[str, dict[str, float]] = {}
        self._strings: dict[str, str] = {}

    # ── ZSet operations ───────────────────────────────────────────────────────

    async def zadd(self, key, mapping):
        self._zsets.setdefault(key, {}).update(mapping)

    async def zremrangebyscore(self, key, min_score, max_score):
        zset = self._zsets.get(key, {})
        lo = float("-inf") if min_score == "-inf" else float(min_score)
        hi = float("+inf") if max_score == "+inf" else float(max_score)
        to_del = [v for v, s in zset.items() if lo <= s <= hi]
        for v in to_del:
            del zset[v]

    async def expire(self, key, ttl):
        pass  # not needed for tests

    async def zrangebyscore(self, key, min_score, max_score, start=0, num=None):
        zset = self._zsets.get(key, {})
        lo = float("-inf") if min_score == "-inf" else float(min_score)
        hi = float("+inf") if max_score == "+inf" else float(max_score)
        items = sorted(
            [(v, s) for v, s in zset.items() if lo <= s <= hi],
            key=lambda x: x[1],
        )
        result = [v for v, _ in items][start:]
        if num is not None:
            result = result[:num]
        return result

    async def zrange(self, key, start, end):
        zset = self._zsets.get(key, {})
        items = sorted(zset.items(), key=lambda x: x[1])
        if end == -1:
            return [v for v, _ in items[-1:]] if items else []
        return [v for v, _ in items[start : end + 1]]

    async def zcard(self, key):
        return len(self._zsets.get(key, {}))

    async def delete(self, key):
        self._zsets.pop(key, None)
        self._strings.pop(key, None)

    # ── String / SET NX ───────────────────────────────────────────────────────

    async def exists(self, key):
        return 1 if key in self._strings else 0

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self._strings:
            return None
        self._strings[key] = str(value)
        return True

    # ── Pipeline ──────────────────────────────────────────────────────────────

    def pipeline(self, transaction=False):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: FakeRedis):
        self._r = redis
        self._cmds = []

    def zadd(self, key, mapping):
        self._cmds.append(("zadd", key, mapping))
        return self

    def zremrangebyscore(self, key, lo, hi):
        self._cmds.append(("zremrangebyscore", key, lo, hi))
        return self

    def expire(self, key, ttl):
        self._cmds.append(("expire", key, ttl))
        return self

    async def execute(self):
        for cmd, *args in self._cmds:
            await getattr(self._r, cmd)(*args)
        return []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.execute()


@pytest.fixture
def fake_redis():
    return FakeRedis()


# ── Time helpers ──────────────────────────────────────────────────────────────

def ts(year=2026, month=1, day=1, hour=9, minute=30, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
