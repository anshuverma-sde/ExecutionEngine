"""Trading service: converts spike signals into persisted trade records.

Flow on signal:
  1. calculate_atm_strike(signal.current_price)
  2. Determine CE (LONG) or PE (SHORT)
  3. simulate_premium(spot, strike, option_type)
  4. Insert Trade via TradeRepository inside a DB transaction
  5. Enqueue Celery notification task AFTER successful commit
     (if broker is unreachable the error is caught — reconciliation picks it up)
"""
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.external.postgres.models import Trade
from app.features.spike_detection.schemas import Signal
from app.features.trading.repository import TradeRepository
from app.features.trading.strike import calculate_atm_strike, simulate_premium

logger = logging.getLogger(__name__)


async def handle_signal(signal: Signal, db: AsyncSession) -> Trade | None:
    """Convert a detected spike signal into a simulated trade.

    Called by the ingestion pipeline (via asyncio.create_task) after detection.
    The DB session is provided by the pipeline's session factory.

    Returns the persisted Trade, or None on failure.
    """
    try:
        strike = calculate_atm_strike(signal.current_price)
        option_type = "CE" if signal.direction == "LONG" else "PE"
        entry_price = simulate_premium(signal.current_price, strike, option_type)

        trade = Trade(
            id=uuid.uuid4(),
            instrument="NIFTY",
            strike=strike,
            option_type=option_type,
            side=signal.direction,
            entry_price=entry_price,
            pnl=0.0,
            signal_reason=signal.reason,
            created_at=signal.ts,
            notification_sent=False,
            notification_failed=False,
            notification_retry_count=0,
        )

        repo = TradeRepository(db)
        trade = await repo.create(trade)
        await db.commit()

    except Exception as exc:
        logger.error("handle_signal failed: %s", exc, exc_info=True)
        await db.rollback()
        return None

    # Post-commit: outside the try block so a failed enqueue cannot trigger
    # db.rollback() on an already-committed transaction.
    logger.info(
        "Trade committed | id=%s | %s NIFTY %d %s | entry=%.2f | %s",
        trade.id,
        trade.side,
        trade.strike,
        trade.option_type,
        trade.entry_price,
        signal.reason,
    )
    _enqueue_notification(str(trade.id))
    return trade


def _enqueue_notification(trade_id: str) -> None:
    """Enqueue the Celery notification task.

    Failure is caught and logged — the Celery Beat reconciliation task
    will detect the unnotified trade within 60 seconds.

    Note: link_error is intentionally NOT used here. Celery's link_error
    prepends the failed task UUID as the first positional arg, which would
    corrupt the trade_id received by notification_dead_letter. Instead,
    send_trade_notification handles dead-lettering explicitly after
    max_retries are exhausted.
    """
    try:
        from app.features.notifications.tasks import send_trade_notification
        send_trade_notification.apply_async(args=[trade_id])
        logger.info("Notification enqueued for trade %s", trade_id)
    except Exception as exc:
        logger.error(
            "Failed to enqueue notification for %s: %s — reconciliation will retry",
            trade_id,
            exc,
        )


class TradingService:
    """Higher-level trading operations used by the API layer."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = TradeRepository(session)

    async def get_trade(self, trade_id: str) -> Trade | None:
        """Retrieve a single trade by UUID string."""
        try:
            uid = uuid.UUID(trade_id)
        except ValueError:
            return None
        return await self._repo.get_by_id(uid)

    async def list_trades(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[Trade], int]:
        """Return paginated trades and total count."""
        return await self._repo.list_trades(page=page, page_size=page_size)
