"""Database query layer for the trading feature (thin async repository)."""
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.external.postgres.models import Trade

logger = logging.getLogger(__name__)

# Trades newer than this are skipped by reconciliation (may still be in-flight)
RECONCILIATION_GRACE_MINUTES = 2


class TradeRepository:
    """Thin async repository — all DB I/O for the trading feature."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, trade: Trade) -> Trade:
        """Persist a new Trade record and return the refreshed ORM instance."""
        self._session.add(trade)
        await self._session.flush()   # assigns DB-generated values (created_at)
        await self._session.refresh(trade)
        return trade

    async def get_by_id(self, trade_id: uuid.UUID) -> Trade | None:
        """Fetch a single trade by primary key. Returns None if not found."""
        return await self._session.get(Trade, trade_id)

    async def list_trades(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[Trade], int]:
        """Return a paginated list of trades (newest first) and the total count."""
        offset = (page - 1) * page_size

        total_result = await self._session.execute(select(func.count(Trade.id)))
        total = total_result.scalar_one()

        trades_result = await self._session.execute(
            select(Trade)
            .order_by(Trade.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        trades = list(trades_result.scalars().all())
        return trades, total

    async def mark_notification_sent(self, trade_id: uuid.UUID) -> None:
        """Set notification_sent=True and record the sent timestamp."""
        await self._session.execute(
            update(Trade)
            .where(Trade.id == trade_id)
            .values(
                notification_sent=True,
                notification_sent_at=datetime.utcnow(),
            )
        )

    async def mark_notification_failed(self, trade_id: uuid.UUID) -> None:
        """Mark a trade's notification as permanently failed."""
        await self._session.execute(
            update(Trade)
            .where(Trade.id == trade_id)
            .values(notification_failed=True)
        )

    async def get_unnotified_trades(self, limit: int = 50) -> list[Trade]:
        """Return trades with no successful notification, past the grace period.

        Excludes trades created within the last RECONCILIATION_GRACE_MINUTES
        (they may still have in-flight Celery tasks).
        Excludes permanently failed notifications.
        """
        cutoff = datetime.utcnow() - timedelta(minutes=RECONCILIATION_GRACE_MINUTES)
        result = await self._session.execute(
            select(Trade)
            .where(Trade.notification_sent.is_(False))
            .where(Trade.notification_failed.is_(False))
            .where(Trade.created_at < cutoff)
            .order_by(Trade.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
