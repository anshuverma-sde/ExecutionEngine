"""Tool implementations for the AI feature — queries the DB and returns structured data."""
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def tool_list_recent_trades(limit: int = 10, session: Any = None) -> list[dict]:
    """Return the N most recent trades as plain dicts for the AI model to reason over."""
    pass


async def tool_get_trade_by_id(trade_id: str, session: Any = None) -> dict | None:
    """Return a single trade by UUID."""
    pass


async def tool_get_spike_summary(symbol: str, session: Any = None) -> dict:
    """Return aggregated spike and trade statistics for the given symbol."""
    pass


async def tool_get_pnl_summary(session: Any = None) -> dict:
    """Return overall simulated P&L across all trades."""
    pass


async def tool_get_latency_stats() -> dict:
    """Return p50/p95/p99 latency metrics from the LatencyCollector."""
    pass


async def tool_get_system_status() -> dict:
    """Return high-level system health: feed state, queue depth, DB connectivity."""
    pass
