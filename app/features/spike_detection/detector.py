"""Spike detector: compares current price against the rolling baseline."""
import logging
from typing import Any

from app.features.spike_detection.schemas import SpikeSignal

logger = logging.getLogger(__name__)

DEFAULT_SPIKE_THRESHOLD_PCT: float = 0.5  # 0.5% deviation triggers a signal


class SpikeDetector:
    """
    Detects price spikes by comparing the latest price against the
    rolling 60-second baseline maintained in the PriceWindow.
    """

    def __init__(
        self,
        price_window: Any,
        threshold_pct: float = DEFAULT_SPIKE_THRESHOLD_PCT,
    ) -> None:
        self._window = price_window
        self.threshold_pct = threshold_pct

    async def detect(self, symbol: str, current_price: float) -> SpikeSignal | None:
        """
        Compare current_price against the rolling baseline.

        Returns a SpikeSignal if the deviation exceeds the threshold,
        otherwise returns None.
        """
        pass
