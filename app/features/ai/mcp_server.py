"""FastMCP server with 6 registered tool definitions for the AI feature."""
import logging

logger = logging.getLogger(__name__)

# Tool schema definitions (registered with FastMCP in TICKET-006)
MCP_TOOLS: list[dict] = [
    {
        "name": "list_recent_trades",
        "description": "Return the N most recent trades.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 10}},
        },
    },
    {
        "name": "get_trade_by_id",
        "description": "Return a single trade by its UUID.",
        "input_schema": {
            "type": "object",
            "properties": {"trade_id": {"type": "string"}},
            "required": ["trade_id"],
        },
    },
    {
        "name": "get_spike_summary",
        "description": "Return spike and trade statistics for a symbol.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_pnl_summary",
        "description": "Return overall simulated P&L across all trades.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_latency_stats",
        "description": "Return p50/p95/p99 pipeline latency metrics.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_system_status",
        "description": "Return high-level system health metrics.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


class MCPServer:
    """Thin wrapper that will host the FastMCP server instance (implemented in TICKET-006)."""

    def __init__(self) -> None:
        self._server = None

    def get_tools(self) -> list[dict]:
        """Return the list of registered tool schemas."""
        return MCP_TOOLS

    async def dispatch(self, tool_name: str, inputs: dict) -> dict:
        """Dispatch a tool call by name and return the result."""
        pass
