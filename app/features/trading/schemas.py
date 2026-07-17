"""Pydantic response schemas for the trading feature."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class TradeResponse(BaseModel):
    """API response schema for a single trade record (mirrors Trade ORM model)."""

    id: uuid.UUID
    instrument: str
    strike: int
    option_type: str          # CE | PE
    side: str                 # LONG | SHORT
    entry_price: float
    pnl: float
    signal_reason: str
    created_at: datetime
    notification_sent: bool
    notification_failed: bool

    model_config = {"from_attributes": True}


class TradeListResponse(BaseModel):
    """Paginated list of trades."""

    items: list[TradeResponse]
    total: int
    page: int
    page_size: int
