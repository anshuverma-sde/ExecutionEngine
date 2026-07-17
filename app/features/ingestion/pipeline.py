"""
Tick ingestion pipeline — THE shared entry point for all market data feeds.

Call `init_pipeline()` once during application startup to wire the
dependencies, then call `ingest_tick()` for every incoming price tick.
"""
import logging
from collections.abc import Callable, Awaitable
from typing import Any

from app.features.ingestion.schemas import Tick

logger = logging.getLogger(__name__)

# Module-level pipeline dependencies (set by init_pipeline)
_price_window: Any | None = None
_spike_detector: Any | None = None
_handle_signal: Callable[..., Awaitable[None]] | None = None
_session_factory: Any | None = None


def init_pipeline(
    price_window: Any,
    spike_detector: Any,
    handle_signal: Callable[..., Awaitable[None]],
    session_factory: Any,
) -> None:
    """Wire up the pipeline dependencies. Must be called before ingest_tick."""
    global _price_window, _spike_detector, _handle_signal, _session_factory
    _price_window = price_window
    _spike_detector = spike_detector
    _handle_signal = handle_signal
    _session_factory = session_factory
    logger.info("Ingestion pipeline initialised")


async def ingest_tick(raw: dict) -> None:
    """
    Entry point for a raw tick dict from any market data feed.

    Steps:
      1. Normalise raw dict → Tick dataclass
      2. Push price into rolling PriceWindow
      3. Run SpikeDetector.detect()
      4. If signal, call handle_signal()
    """
    pass
