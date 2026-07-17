"""Trading service: handles spike signals and creates trade records."""
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def handle_signal(signal: Any, session_factory: Any) -> None:
    """
    Respond to a SpikeSignal by computing the ATM strike, simulating
    the premium, persisting the trade and dispatching a notification task.

    Args:
        signal: A SpikeSignal instance from the spike detection feature.
        session_factory: Callable that returns an async DB session context manager.
    """
    pass


class TradingService:
    """Higher-level trading operations used by the API layer."""

    def __init__(self, session: Any) -> None:
        self._session = session

    async def get_trade(self, trade_id: str) -> Any | None:
        """Retrieve a single trade by ID."""
        pass

    async def list_trades(self, page: int = 1, page_size: int = 20) -> tuple[list[Any], int]:
        """Return a paginated list of all trades."""
        pass
