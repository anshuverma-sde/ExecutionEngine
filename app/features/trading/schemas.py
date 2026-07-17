"""Pydantic schemas for the trading feature."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class TradeResponse(BaseModel):
    """API response schema for a single trade record."""

    id: uuid.UUID
    symbol: str
    strike: int
    option_type: str
    premium: float
    quantity: int
    signal_price: float
    status: str
    notification_sent: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TradeListResponse(BaseModel):
    """Paginated list of trades."""

    items: list[TradeResponse]
    total: int
    page: int
    page_size: int
