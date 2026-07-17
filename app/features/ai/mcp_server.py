"""MCP-compatible tool server for the AI trade intelligence layer.

Exposes 6 tools as defined in the assignment spec (Part 5):
  1. get_last_trade()
  2. get_open_positions()
  3. get_pnl_summary()
  4. get_spike_events()
  5. get_best_strike_accuracy()
  6. generate_trade_chart()

Tool schemas are in OpenAI function-calling format (compatible with Groq).
"""
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.ai import tools as _tools

logger = logging.getLogger(__name__)


# ── Tool schemas (OpenAI function-calling / Groq format) ─────────────────────

MCP_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_last_trade",
            "description": "Return the most recent trade recorded by the execution engine.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_open_positions",
            "description": (
                "Return the most recent simulated open positions. "
                "All trades are treated as open (no exit in simulation)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of positions to return (1-100, default 20).",
                        "default": 20,
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pnl_summary",
            "description": (
                "Return overall simulated P&L statistics: total, average, max, min, "
                "and breakdowns by LONG/SHORT and CE/PE."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spike_events",
            "description": (
                "Return recent spike-triggered trade events with their signal details "
                "(direction, strike, signal reason, entry price)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of spike events to return (1-100, default 10).",
                        "default": 10,
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_best_strike_accuracy",
            "description": (
                "Return the strike price and option type that generated the highest "
                "total simulated P&L. Also returns top-5 strikes for comparison."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_trade_chart",
            "description": (
                "Generate a text-based chart summarising the last 20 trades: "
                "direction, strike, entry price, P&L, and overall win rate."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


class MCPServer:
    """Manages tool dispatch for the AI agentic loop."""

    def get_tools(self) -> list[dict]:
        """Return all registered tool schemas (OpenAI/Groq function-calling format)."""
        return MCP_TOOLS

    async def dispatch(
        self, tool_name: str, inputs: dict, session: AsyncSession | None = None
    ) -> Any:
        """Route a tool call by name and return the result.

        Args:
            tool_name: One of the 6 registered tool names.
            inputs:    Tool input parameters from the model.
            session:   Async SQLAlchemy session (required for DB-backed tools).

        Returns:
            JSON-serialisable result dict or list.
        """
        logger.debug("MCP dispatch: tool=%s inputs=%s", tool_name, inputs)

        if tool_name == "get_last_trade":
            return await _tools.tool_get_last_trade(session=session)

        elif tool_name == "get_open_positions":
            return await _tools.tool_get_open_positions(
                limit=inputs.get("limit", 20), session=session
            )

        elif tool_name == "get_pnl_summary":
            return await _tools.tool_get_pnl_summary(session=session)

        elif tool_name == "get_spike_events":
            return await _tools.tool_get_spike_events(
                limit=inputs.get("limit", 10), session=session
            )

        elif tool_name == "get_best_strike_accuracy":
            return await _tools.tool_get_best_strike_accuracy(session=session)

        elif tool_name == "generate_trade_chart":
            return await _tools.tool_generate_trade_chart(session=session)

        else:
            raise ValueError(f"Unknown MCP tool: {tool_name!r}")
