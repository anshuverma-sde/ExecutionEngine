"""Tests for the ingestion pipeline."""
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.ingestion import pipeline as _pipeline
from app.metrics.latency import latency_collector
from tests.conftest import ts


@pytest.fixture(autouse=True)
def reset_pipeline():
    """Reset pipeline module globals and latency before each test."""
    latency_collector.reset()
    _pipeline._price_window = None
    _pipeline._spike_detector = None
    _pipeline._handle_signal = None
    _pipeline._session_factory = None
    yield
    _pipeline._price_window = None
    _pipeline._spike_detector = None
    _pipeline._handle_signal = None
    _pipeline._session_factory = None


def make_mock_window():
    w = AsyncMock()
    w.append = AsyncMock()
    return w


def make_mock_detector(signal=None):
    d = AsyncMock()
    d.detect = AsyncMock(return_value=signal)
    return d


@pytest.mark.asyncio
class TestIngestTickNotInitialised:
    async def test_returns_none_when_not_init(self):
        result = await _pipeline.ingest_tick("13", 22000.0, ts())
        assert result is None

    async def test_still_records_no_latency_when_not_init(self):
        await _pipeline.ingest_tick("13", 22000.0, ts())
        assert latency_collector.stats()["count"] == 0


@pytest.mark.asyncio
class TestIngestTickLatency:
    async def test_records_latency_on_each_tick(self, fake_redis):
        from app.external.redis.window import PriceWindow
        from app.features.spike_detection.detector import SpikeDetector

        window = PriceWindow(fake_redis)
        detector = SpikeDetector(window)
        session_factory = MagicMock()
        _pipeline.init_pipeline(window, detector, AsyncMock(), session_factory)

        t = ts()
        for i in range(5):
            await _pipeline.ingest_tick("13", 22000.0 + i, t + timedelta(seconds=i))

        assert latency_collector.stats()["count"] == 5

    async def test_latency_recorded_even_on_no_signal(self, fake_redis):
        from app.external.redis.window import PriceWindow
        from app.features.spike_detection.detector import SpikeDetector

        window = PriceWindow(fake_redis)
        detector = SpikeDetector(window)
        _pipeline.init_pipeline(window, detector, AsyncMock(), MagicMock())

        await _pipeline.ingest_tick("13", 22000.0, ts())
        assert latency_collector.stats()["count"] == 1


@pytest.mark.asyncio
class TestIngestTickSignalDispatch:
    async def test_returns_none_when_no_signal(self, fake_redis):
        from app.external.redis.window import PriceWindow
        window = PriceWindow(fake_redis)
        detector = make_mock_detector(signal=None)
        _pipeline.init_pipeline(window, detector, AsyncMock(), MagicMock())
        result = await _pipeline.ingest_tick("13", 22000.0, ts())
        assert result is None

    async def test_returns_signal_when_detected(self, fake_redis):
        from app.features.spike_detection.schemas import Signal
        from app.external.redis.window import PriceWindow

        mock_signal = Signal(
            security_id="13",
            direction="LONG",
            current_price=23100.0,
            reference_price=22000.0,
            pct_change=5.0,
            ts=ts(),
            reason="+5.00% spike in 60s",
        )
        window = PriceWindow(fake_redis)
        detector = make_mock_detector(signal=mock_signal)

        mock_sf = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_sf.return_value = mock_ctx

        _pipeline.init_pipeline(window, detector, AsyncMock(), mock_sf)
        result = await _pipeline.ingest_tick("13", 23100.0, ts())
        assert result is mock_signal
