"""Pydantic response schemas for the trading feature."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TradeResponse(BaseModel):
    """A single simulated trade record created when a spike signal fires."""

    id: uuid.UUID = Field(description="Unique trade identifier (UUID v4)")
    instrument: str = Field(description="Underlying instrument name", example="NIFTY")
    strike: int = Field(description="ATM strike price (nearest 50-point increment)", example=22450)
    option_type: str = Field(description="Option type: CE (Call) on LONG signal, PE (Put) on SHORT signal", example="CE")
    side: str = Field(description="Signal direction that triggered this trade: LONG or SHORT", example="LONG")
    entry_price: float = Field(description="Simulated option entry premium in INR", example=94.9)
    pnl: float = Field(description="Realised P&L (0.0 — no exit simulation in current scope)", example=0.0)
    signal_reason: str = Field(description="Human-readable reason for the spike signal", example="+5.23% spike in 60s")
    created_at: datetime = Field(description="Timestamp when the spike signal fired (UTC)")
    notification_sent: bool = Field(description="True if the Celery notification task delivered the webhook successfully")
    notification_failed: bool = Field(description="True if all retry attempts were exhausted without delivery")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "instrument": "NIFTY",
                "strike": 22450,
                "option_type": "CE",
                "side": "LONG",
                "entry_price": 94.9,
                "pnl": 0.0,
                "signal_reason": "+5.23% spike in 60s",
                "created_at": "2026-07-10T09:31:05Z",
                "notification_sent": True,
                "notification_failed": False,
            }
        },
    }


class TradeListResponse(BaseModel):
    """Paginated list of trade records."""

    items: list[TradeResponse] = Field(description="Trade records for this page, newest first")
    total: int = Field(description="Total number of trades across all pages", example=42)
    page: int = Field(description="Current page number (1-based)", example=1)
    page_size: int = Field(description="Number of items per page", example=20)
