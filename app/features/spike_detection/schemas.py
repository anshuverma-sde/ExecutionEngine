"""Schemas for the spike detection feature."""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class Signal:
    """Emitted when a ±5% price move over 60 seconds is detected.

    direction: "LONG"  → price rose  >= +5%  → buy ATM Call (CE)
               "SHORT" → price fell  <= -5%  → buy ATM Put  (PE)
    reason   : human-readable string stored verbatim in trades.signal_reason
    """

    security_id: str
    direction: Literal["LONG", "SHORT"]
    current_price: float       # Pt
    reference_price: float     # P(t-60)
    pct_change: float          # percentage, e.g. +5.23 or -6.01
    ts: datetime               # UTC timestamp of the triggering tick
    reason: str                # e.g. "+5.23% spike in 60s"
