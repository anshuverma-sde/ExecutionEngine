"""Schemas for the spike detection feature."""
from dataclasses import dataclass, field
import time


@dataclass
class SpikeSignal:
    """Emitted when a price spike exceeding the threshold is detected."""

    symbol: str
    current_price: float
    baseline_price: float
    spike_pct: float
    direction: str          # "up" | "down"
    timestamp: float = field(default_factory=time.time)
