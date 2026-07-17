"""Pydantic schemas for DhanHQ WebSocket feed messages."""
from pydantic import BaseModel


class DhanTick(BaseModel):
    """A single price tick received from the DhanHQ market feed."""

    symbol: str
    ltp: float          # Last traded price
    timestamp: float    # Unix epoch seconds
    volume: int = 0
    oi: int = 0         # Open interest


class DhanFeedMessage(BaseModel):
    """Raw message envelope from the DhanHQ WebSocket feed."""

    type: str           # e.g. "tick", "heartbeat", "error"
    data: dict | None = None
