"""Schemas for the notifications feature."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationPayload(BaseModel):
    """Payload sent to the webhook endpoint for each trade notification."""

    trade_id: uuid.UUID
    symbol: str
    strike: int
    option_type: str
    premium: float
    signal_price: float
    message: str
    timestamp: datetime
