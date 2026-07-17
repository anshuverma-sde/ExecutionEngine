"""Tests for the Redis rolling price window."""
import json
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio

from app.external.redis.window import PriceWindow
from tests.conftest import ts


@pytest.fixture
def window(fake_redis):
    return PriceWindow(fake_redis)


@pytest.mark.asyncio
class TestPriceWindowAppend:
    async def test_append_stores_entry(self, window, fake_redis):
        t = ts()
        await window.append("13", 22000.0, t)
        size = await window.window_size("13")
        assert size == 1

    async def test_append_multiple_entries(self, window):
        t = ts()
        for i in range(5):
            await window.append("13", 22000.0 + i, t + timedelta(seconds=i))
        assert await window.window_size("13") == 5

    async def test_evicts_old_entries(self, window):
        old_ts = ts()
        new_ts = old_ts + timedelta(seconds=61)
        await window.append("13", 22000.0, old_ts)
        await window.append("13", 22050.0, new_ts)
        # After second append, old entry (>60s ago) must be evicted
        assert await window.window_size("13") == 1

    async def test_keeps_recent_entries(self, window):
        t = ts()
        await window.append("13", 22000.0, t)
        await window.append("13", 22010.0, t + timedelta(seconds=30))
        # Both within 60s window
        assert await window.window_size("13") == 2

    async def test_separate_keys_per_security(self, window):
        t = ts()
        await window.append("13", 22000.0, t)
        await window.append("99", 50000.0, t)
        assert await window.window_size("13") == 1
        assert await window.window_size("99") == 1


@pytest.mark.asyncio
class TestGetPriceAtTMinus60:
    async def test_returns_none_on_empty_window(self, window):
        result = await window.get_price_at_t_minus_60("13", ts())
        assert result is None

    async def test_returns_none_when_all_entries_evicted(self, window):
        # Append a single entry, then query past the 60s TTL so it's evicted
        t = ts()
        await window.append("13", 22000.0, t)
        # At t+61s the entry (score=t) is below cutoff (t+1s) → evicted → None
        result = await window.get_price_at_t_minus_60("13", t + timedelta(seconds=61))
        assert result is None

    async def test_returns_oldest_price_within_window(self, window):
        t = ts()
        await window.append("13", 22000.0, t)
        await window.append("13", 22100.0, t + timedelta(seconds=30))
        # At t+55s cutoff = t-5s; both entries are in range; oldest is 22000 at t
        result = await window.get_price_at_t_minus_60("13", t + timedelta(seconds=55))
        assert result == 22000.0

    async def test_get_latest_price(self, window):
        t = ts()
        await window.append("13", 22000.0, t)
        await window.append("13", 22999.0, t + timedelta(seconds=1))
        latest = await window.get_latest_price("13")
        assert latest == 22999.0

    async def test_flush_clears_window(self, window):
        t = ts()
        await window.append("13", 22000.0, t)
        await window.flush("13")
        assert await window.window_size("13") == 0
