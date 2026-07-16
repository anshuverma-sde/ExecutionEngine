"""ORM models for the execution engine."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.external.postgres.engine import Base


class Trade(Base):
    """Represents a simulated options trade triggered by a spike signal."""

    __tablename__ = "trades"

    # Core fields (per spec)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instrument: Mapped[str] = mapped_column(String(20), nullable=False)
    strike: Mapped[int] = mapped_column(Integer, nullable=False)
    option_type: Mapped[str] = mapped_column(String(2), nullable=False)   # CE | PE
    side: Mapped[str] = mapped_column(String(5), nullable=False)           # LONG | SHORT
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    signal_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Notification tracking (required by reconciliation — TICKET-009)
    notification_sent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    notification_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notification_failed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    notification_retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    __table_args__ = (
        Index("ix_trades_created_at", "created_at"),
        Index("ix_trades_notification_sent", "notification_sent"),
        Index("ix_trades_strike", "strike"),
    )
