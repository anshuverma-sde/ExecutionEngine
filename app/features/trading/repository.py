"""Database query layer for the trading feature (thin async wrapper)."""
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class TradeRepository:
    """Thin async repository for Trade ORM operations."""

    def __init__(self, session: Any) -> None:
        self._session = session

    async def create(self, trade_data: dict) -> Any:
        """Persist a new Trade record and return the ORM instance."""
        pass

    async def get_by_id(self, trade_id: uuid.UUID) -> Any | None:
        """Fetch a single trade by primary key."""
        pass

    async def list_trades(self, page: int = 1, page_size: int = 20) -> tuple[list[Any], int]:
        """Return a paginated list of trades and the total count."""
        pass

    async def mark_notification_sent(self, trade_id: uuid.UUID) -> None:
        """Set notification_sent=True for the given trade."""
        pass

    async def get_unnotified_trades(self) -> list[Any]:
        """Return trades where notification_sent=False."""
        pass
