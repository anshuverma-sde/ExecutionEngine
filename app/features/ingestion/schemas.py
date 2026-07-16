"""Schemas for the tick ingestion pipeline."""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Tick:
    """A single normalised price tick — canonical internal representation.

    Both the live WebSocket consumer and the replay endpoint produce this type
    before handing off to ingest_tick().
    """

    security_id: str   # e.g. "13" for NIFTY 50
    ltp: float         # Last traded price
    ts: datetime       # UTC timestamp of the tick
