"""Schemas for the tick ingestion pipeline."""
from dataclasses import dataclass, field
import time


@dataclass
class Tick:
    """A single normalised price tick from any market data feed."""

    symbol: str
    price: float
    timestamp: float = field(default_factory=time.time)
    volume: int = 0
    source: str = "unknown"
