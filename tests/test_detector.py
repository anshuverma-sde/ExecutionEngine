"""Tests for the SpikeDetector.

Key timing rule: an entry appended at time T is in the 60s window as long as
the query timestamp is < T + 60s. At T+61s the entry is evicted.
So detector tests use a 30-second gap between reference and current tick.
"""
from datetime import timedelta

import pytest

from app.external.redis.window import PriceWindow
from app.features.spike_detection.detector import SpikeDetector
from tests.conftest import ts


def make_detector(fake_redis):
    window = PriceWindow(fake_redis)
    return SpikeDetector(window), window


@pytest.mark.asyncio
class TestColdStart:
    async def test_returns_none_with_no_history(self, fake_redis):
        detector, _ = make_detector(fake_redis)
        result = await detector.detect("13", 22000.0, ts())
        assert result is None

    async def test_returns_none_when_reference_evicted(self, fake_redis):
        # Reference at t is evicted when we query at t+61s (cutoff = t+1s > t)
        detector, window = make_detector(fake_redis)
        t = ts()
        await window.append("13", 22000.0, t)
        result = await detector.detect("13", 23200.0, t + timedelta(seconds=61))
        assert result is None


@pytest.mark.asyncio
class TestLongSignal:
    async def test_fires_on_exactly_5_percent_rise(self, fake_redis):
        detector, window = make_detector(fake_redis)
        t = ts()
        await window.append("13", 22000.0, t)
        # Detect at t+30s — reference (22000 at t) still in window
        # 23100 / 22000 = 1.05 → exactly +5%
        signal = await detector.detect("13", 23100.0, t + timedelta(seconds=30))
        assert signal is not None
        assert signal.direction == "LONG"
        assert signal.security_id == "13"
        assert signal.reference_price == 22000.0
        assert signal.current_price == 23100.0

    async def test_fires_above_5_percent(self, fake_redis):
        detector, window = make_detector(fake_redis)
        t = ts()
        await window.append("13", 20000.0, t)
        # 21500 / 20000 = 1.075 → +7.5%
        signal = await detector.detect("13", 21500.0, t + timedelta(seconds=30))
        assert signal is not None
        assert signal.direction == "LONG"

    async def test_no_signal_below_5_percent(self, fake_redis):
        detector, window = make_detector(fake_redis)
        t = ts()
        await window.append("13", 22000.0, t)
        # 23078 / 22000 ≈ +4.9% — just below threshold
        signal = await detector.detect("13", 23078.0, t + timedelta(seconds=30))
        assert signal is None

    async def test_no_signal_on_flat_price(self, fake_redis):
        detector, window = make_detector(fake_redis)
        t = ts()
        await window.append("13", 22000.0, t)
        signal = await detector.detect("13", 22000.0, t + timedelta(seconds=30))
        assert signal is None


@pytest.mark.asyncio
class TestShortSignal:
    async def test_fires_on_exactly_5_percent_drop(self, fake_redis):
        detector, window = make_detector(fake_redis)
        t = ts()
        await window.append("13", 22000.0, t)
        # 20900 / 22000 ≈ -5% exactly
        signal = await detector.detect("13", 20900.0, t + timedelta(seconds=30))
        assert signal is not None
        assert signal.direction == "SHORT"

    async def test_fires_below_minus_5_percent(self, fake_redis):
        detector, window = make_detector(fake_redis)
        t = ts()
        await window.append("13", 22000.0, t)
        # 20000 / 22000 ≈ -9.1%
        signal = await detector.detect("13", 20000.0, t + timedelta(seconds=30))
        assert signal is not None
        assert signal.direction == "SHORT"

    async def test_no_signal_above_minus_5_percent(self, fake_redis):
        detector, window = make_detector(fake_redis)
        t = ts()
        await window.append("13", 22000.0, t)
        # 20922 / 22000 ≈ -4.9%
        signal = await detector.detect("13", 20922.0, t + timedelta(seconds=30))
        assert signal is None


@pytest.mark.asyncio
class TestCooldown:
    async def test_cooldown_suppresses_second_signal(self, fake_redis):
        detector, window = make_detector(fake_redis)
        t = ts()
        await window.append("13", 22000.0, t)

        # First detect at t+30s — fires (reference = 22000 at t)
        s1 = await detector.detect("13", 23100.0, t + timedelta(seconds=30))
        assert s1 is not None

        # Seed a new reference for the second attempt
        t2 = t + timedelta(seconds=30)
        await window.append("13", 22000.0, t2)
        # Second detect at t+50s (reference 22000 still in window) — cooldown active
        s2 = await detector.detect("13", 23100.0, t2 + timedelta(seconds=20))
        assert s2 is None

    async def test_cooldown_is_per_security(self, fake_redis):
        detector, window = make_detector(fake_redis)
        t = ts()
        await window.append("13", 22000.0, t)
        await window.append("99", 50000.0, t)
        t2 = t + timedelta(seconds=30)

        # Security 13 fires
        s1 = await detector.detect("13", 23100.0, t2)
        assert s1 is not None

        # Security 99 — different cooldown key, should also fire
        # 52600 / 50000 = 1.052 → +5.2%
        s2 = await detector.detect("99", 52600.0, t2)
        assert s2 is not None


@pytest.mark.asyncio
class TestEdgeCases:
    async def test_zero_reference_price_skipped(self, fake_redis):
        detector, window = make_detector(fake_redis)
        t = ts()
        await window.append("13", 0.0, t)
        signal = await detector.detect("13", 22000.0, t + timedelta(seconds=30))
        assert signal is None

    async def test_signal_reason_format_long(self, fake_redis):
        detector, window = make_detector(fake_redis)
        t = ts()
        await window.append("13", 22000.0, t)
        signal = await detector.detect("13", 23100.0, t + timedelta(seconds=30))
        assert signal is not None
        assert "spike in 60s" in signal.reason
        assert "+" in signal.reason

    async def test_signal_reason_format_short(self, fake_redis):
        detector, window = make_detector(fake_redis)
        t = ts()
        await window.append("13", 22000.0, t)
        signal = await detector.detect("13", 20900.0, t + timedelta(seconds=30))
        assert signal is not None
        assert "spike in 60s" in signal.reason
