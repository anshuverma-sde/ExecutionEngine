"""FastMCP server with 6 registered tools for the AI trade intelligence feature.

The MCPServer is instantiated once at application startup (via lifespan).
It dispatches tool calls from the agentic loop in AnthropicClient.answer().

Tools registered:
  1. list_recent_trades    — last N trades from DB
  2. get_trade_by_id       — single trade lookup by UUID
  3. get_spike_summary     — per-symbol spike / trade aggregates
  4. get_pnl_summary       — overall P&L across all trades
  5. get_latency_stats     — tick-to-signal latency percentiles
  6. get_system_status     — Redis / Postgres / feed health check
"""
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.ai import tools as _tools

logger = logging.getLogger(__name__)

# ── Tool schema registry (Anthropic tool_use format) ─────────────────────────

MCP_TOOLS: list[dict] = [
    {
        "name": "list_recent_trades",
        "description": (
            "Return the N most recent trades recorded by the execution engine. "
            "Use this to understand recent trading activity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of trades to return (1-100, default 10).",
                    "default": 10,
                }
            },
        },
    },
    {
        "name": "get_trade_by_id",
        "description": "Return full details of a single trade given its UUID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "trade_id": {
                    "type": "string",
                    "description": "UUID of the trade to retrieve.",
                }
            },
            "required": ["trade_id"],
        },
    },
    {
        "name": "get_spike_summary",
        "description": (
            "Return aggregated spike and trade statistics for a given trading symbol "
            "(e.g. 'NIFTY'). Includes trade count, P&L, and long/short breakdown."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading instrument symbol, e.g. 'NIFTY'.",
                }
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_pnl_summary",
        "description": (
            "Return overall simulated P&L statistics across all trades: "
            "total, average, max, min, and notification delivery stats."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_latency_stats",
        "description": (
            "Return tick-to-signal pipeline latency percentiles (p50, p95, p99, max). "
            "Also reports whether the p99 < 50ms SLA target is currently met."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_system_status",
        "description": (
            "Return high-level system health: Redis connectivity, Postgres connectivity, "
            "and a latency summary. Use this to diagnose infrastructure issues."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


class MCPServer:
    """Manages tool dispatch for the AI agentic loop.

    Instantiated once at app startup and injected into AIService.
    The session parameter is provided per-request by the FastAPI dependency.
    """

    def get_tools(self) -> list[dict]:
        """Return all registered tool schemas (Anthropic tool_use format)."""
        return MCP_TOOLS

    async def dispatch(self, tool_name: str, inputs: dict, session: AsyncSession | None = None) -> Any:
        """Route a tool call by name and return the result.

        Args:
            tool_name: One of the 6 registered tool names.
            inputs:    Tool input parameters from the model.
            session:   Async SQLAlchemy session (for DB-backed tools).

        Returns:
            JSON-serialisable result dict or list.

        Raises:
            ValueError: If tool_name is not registered.
        """
        logger.debug("MCP dispatch: tool=%s inputs=%s", tool_name, inputs)

        if tool_name == "list_recent_trades":
            return await _tools.tool_list_recent_trades(
                limit=inputs.get("limit", 10),
                session=session,
            )

        elif tool_name == "get_trade_by_id":
            return await _tools.tool_get_trade_by_id(
                trade_id=inputs["trade_id"],
                session=session,
            )

        elif tool_name == "get_spike_summary":
            return await _tools.tool_get_spike_summary(
                symbol=inputs["symbol"],
                session=session,
            )

        elif tool_name == "get_pnl_summary":
            return await _tools.tool_get_pnl_summary(session=session)

        elif tool_name == "get_latency_stats":
            return await _tools.tool_get_latency_stats()

        elif tool_name == "get_system_status":
            return await _tools.tool_get_system_status()

        else:
            raise ValueError(f"Unknown MCP tool: {tool_name!r}")
