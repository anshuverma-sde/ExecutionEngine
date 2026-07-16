# Plan: TICKET-010 — MCP Server & AI Trade Intelligence Layer

## Branch
```bash
git checkout -b feature/TICKET-010-mcp-ai-layer
```

## Implementation Steps

### Step 1 — `app/features/ai/tools.py` (DB query functions)
```python
import base64
import io
import logging
from datetime import datetime, date
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.external.postgres.models import Trade

logger = logging.getLogger(__name__)


async def db_get_last_trade(db: AsyncSession) -> dict | None:
    result = await db.execute(
        select(Trade).order_by(desc(Trade.created_at)).limit(1)
    )
    trade = result.scalar_one_or_none()
    return _trade_to_dict(trade) if trade else None


async def db_get_open_positions(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Trade).where(Trade.pnl == 0.0).order_by(desc(Trade.created_at))
    )
    return [_trade_to_dict(t) for t in result.scalars().all()]


async def db_get_pnl_summary(db: AsyncSession) -> dict:
    result = await db.execute(select(Trade))
    trades = result.scalars().all()
    if not trades:
        return {"total_trades": 0, "total_pnl": 0}
    
    total_pnl = sum(t.pnl for t in trades)
    ce_trades = [t for t in trades if t.option_type == "CE"]
    pe_trades = [t for t in trades if t.option_type == "PE"]
    winners = [t for t in trades if t.pnl > 0]
    
    return {
        "total_trades": len(trades),
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(len(winners) / len(trades) * 100, 1),
        "ce": {
            "count": len(ce_trades),
            "total_pnl": round(sum(t.pnl for t in ce_trades), 2),
        },
        "pe": {
            "count": len(pe_trades),
            "total_pnl": round(sum(t.pnl for t in pe_trades), 2),
        },
        "long": {
            "count": len([t for t in trades if t.side == "LONG"]),
            "total_pnl": round(sum(t.pnl for t in trades if t.side == "LONG"), 2),
        },
        "short": {
            "count": len([t for t in trades if t.side == "SHORT"]),
            "total_pnl": round(sum(t.pnl for t in trades if t.side == "SHORT"), 2),
        },
    }


async def db_get_spike_events(db: AsyncSession, limit: int = 20) -> list[dict]:
    result = await db.execute(
        select(Trade).order_by(desc(Trade.created_at)).limit(limit)
    )
    trades = result.scalars().all()
    return [
        {
            "trade_id": str(t.id),
            "signal_reason": t.signal_reason,
            "direction": t.side,
            "strike": t.strike,
            "option_type": t.option_type,
            "ts": t.created_at.isoformat(),
        }
        for t in trades
    ]


async def db_get_best_strike_accuracy(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(
            Trade.strike,
            func.avg(Trade.pnl).label("avg_pnl"),
            func.count(Trade.id).label("count"),
        )
        .group_by(Trade.strike)
        .order_by(desc(func.avg(Trade.pnl)))
    )
    rows = result.all()
    return [
        {"strike": r.strike, "avg_pnl": round(r.avg_pnl, 2), "trade_count": r.count}
        for r in rows
    ]


async def db_generate_trade_chart(db: AsyncSession) -> dict:
    result = await db.execute(
        select(Trade).order_by(Trade.created_at).limit(200)
    )
    trades = result.scalars().all()
    
    if not trades:
        return {"error": "No trades to chart"}
    
    timestamps = [t.created_at for t in trades]
    cumulative_pnl = []
    running = 0
    for t in trades:
        running += t.pnl
        cumulative_pnl.append(running)
    
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(timestamps, cumulative_pnl, color="green" if cumulative_pnl[-1] >= 0 else "red")
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_title("Cumulative PnL Over Time")
    ax.set_xlabel("Time")
    ax.set_ylabel("PnL (INR)")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    
    return {
        "image_base64": base64.b64encode(buf.read()).decode(),
        "format": "png",
        "trade_count": len(trades),
    }


def _trade_to_dict(trade: Trade) -> dict:
    return {
        "id": str(trade.id),
        "instrument": trade.instrument,
        "strike": trade.strike,
        "option_type": trade.option_type,
        "side": trade.side,
        "entry_price": trade.entry_price,
        "pnl": trade.pnl,
        "signal_reason": trade.signal_reason,
        "created_at": trade.created_at.isoformat(),
        "notification_sent": trade.notification_sent,
    }
```

### Step 2 — `app/features/ai/mcp_server.py`
```python
from fastmcp import FastMCP
from app.features.ai.tools import (
    db_get_last_trade, db_get_open_positions, db_get_pnl_summary,
    db_get_spike_events, db_get_best_strike_accuracy, db_generate_trade_chart
)
from app.external.postgres.engine import AsyncSessionLocal

mcp = FastMCP("Instant Strike Trade Intelligence")


@mcp.tool()
async def get_last_trade() -> dict:
    """Get the most recently executed trade."""
    async with AsyncSessionLocal() as db:
        result = await db_get_last_trade(db)
    return result or {"error": "No trades recorded yet"}


@mcp.tool()
async def get_open_positions() -> list:
    """Get all currently open positions (no exit price recorded)."""
    async with AsyncSessionLocal() as db:
        return await db_get_open_positions(db)


@mcp.tool()
async def get_pnl_summary() -> dict:
    """Get PnL summary broken down by CE/PE, LONG/SHORT, with win rate."""
    async with AsyncSessionLocal() as db:
        return await db_get_pnl_summary(db)


@mcp.tool()
async def get_spike_events(limit: int = 20) -> list:
    """Get recent spike detection events (max 20)."""
    async with AsyncSessionLocal() as db:
        return await db_get_spike_events(db, limit=limit)


@mcp.tool()
async def get_best_strike_accuracy() -> list:
    """Rank strike prices by average PnL to find most accurate selections."""
    async with AsyncSessionLocal() as db:
        return await db_get_best_strike_accuracy(db)


@mcp.tool()
async def generate_trade_chart() -> dict:
    """Generate cumulative PnL timeline chart. Returns base64-encoded PNG."""
    async with AsyncSessionLocal() as db:
        return await db_generate_trade_chart(db)
```

### Step 3 — `app/features/ai/service.py` (Claude API agentic loop)
```python
import json
import logging
from typing import Any

import anthropic

from app.core.config import settings
from app.features.ai.mcp_server import mcp

logger = logging.getLogger(__name__)

TOOL_SCHEMAS = [
    {"name": "get_last_trade", "description": "Get the most recently executed trade.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_open_positions", "description": "Get all currently open positions.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_pnl_summary", "description": "Get PnL summary by CE/PE, LONG/SHORT.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_spike_events", "description": "Get recent spike events.", "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 20}}}},
    {"name": "get_best_strike_accuracy", "description": "Rank strikes by average PnL.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "generate_trade_chart", "description": "Generate PnL timeline chart as base64 PNG.", "input_schema": {"type": "object", "properties": {}}},
]

TOOL_DISPATCH = {
    "get_last_trade": mcp.get_tool("get_last_trade"),
    "get_open_positions": mcp.get_tool("get_open_positions"),
    "get_pnl_summary": mcp.get_tool("get_pnl_summary"),
    "get_spike_events": mcp.get_tool("get_spike_events"),
    "get_best_strike_accuracy": mcp.get_tool("get_best_strike_accuracy"),
    "generate_trade_chart": mcp.get_tool("generate_trade_chart"),
}


async def answer_question(question: str) -> dict:
    if not settings.ANTHROPIC_API_KEY:
        return {"answer": "AI layer not configured. Set ANTHROPIC_API_KEY in .env.", "tools_used": []}
    
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": question}]
    tools_used = []
    
    for _ in range(5):  # max 5 tool rounds
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            tools=TOOL_SCHEMAS,
            messages=messages,
            system="You are a trading assistant. Use the available tools to answer questions about trades and market data. Be concise and specific.",
        )
        
        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if hasattr(b, "text")), "")
            return {"answer": text, "tools_used": tools_used}
        
        # Execute tool calls
        tool_results = []
        messages.append({"role": "assistant", "content": response.content})
        
        for block in response.content:
            if block.type == "tool_use":
                tools_used.append(block.name)
                tool_fn = TOOL_DISPATCH.get(block.name)
                if tool_fn:
                    try:
                        result = await tool_fn(**block.input)
                    except Exception as e:
                        result = {"error": str(e)}
                else:
                    result = {"error": f"Unknown tool: {block.name}"}
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })
        
        messages.append({"role": "user", "content": tool_results})
    
    return {"answer": "I could not complete the query within the allowed rounds.", "tools_used": tools_used}
```

### Step 4 — `app/features/ai/router.py`
```python
from fastapi import APIRouter
from pydantic import BaseModel
from app.features.ai.service import answer_question

router = APIRouter(tags=["AI"])

class AskRequest(BaseModel):
    question: str

@router.post("/ask")
async def ask(body: AskRequest):
    """
    Natural language trade query powered by Claude AI.
    
    Examples:
    - "What was the last trade?"
    - "Show today's losing trades."
    - "Which strike performed best?"
    - "Compare CE vs PE profitability."
    """
    result = await answer_question(body.question)
    return result
```

### Step 5 — `app/external/anthropic/client.py`
```python
import anthropic
from app.core.config import settings

def get_anthropic_client() -> anthropic.AsyncAnthropic:
    """Return a configured async Anthropic client."""
    return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
```

## Verification
```bash
# Ensure some trades exist first (via replay)
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What was the last trade?"}'

curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Compare CE vs PE profitability."}'
```

## Commit Message
```
feat: add MCP server with 6 trade intelligence tools and Claude-powered /ask endpoint
```
