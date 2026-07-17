"""Tool implementations for the AI MCP layer.

Implements the 6 tools specified in the assignment:
  1. get_last_trade()          — most recent trade record
  2. get_open_positions()      — trades with no exit (all are simulated, so all "open")
  3. get_pnl_summary()         — overall P&L statistics
  4. get_spike_events()        — recent spike-triggered trade events
  5. get_best_strike_accuracy() — strike that generated highest total P&L
  6. generate_trade_chart()    — ASCII/text summary chart of recent trade history
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.external.postgres.models import Trade
from app.metrics.latency import latency_collector

logger = logging.getLogger(__name__)


async def tool_get_last_trade(session: AsyncSession) -> dict:
    """Return the most recent trade record."""
    result = await session.execute(
        select(Trade).order_by(Trade.created_at.desc()).limit(1)
    )
    trade = result.scalars().first()
    if trade is None:
        return {"message": "No trades found"}
    return {
        "id": str(trade.id),
        "instrument": trade.instrument,
        "strike": trade.strike,
        "option_type": trade.option_type,
        "side": trade.side,
        "entry_price": trade.entry_price,
        "pnl": trade.pnl,
        "signal_reason": trade.signal_reason,
        "created_at": trade.created_at.isoformat() if trade.created_at else None,
        "notification_sent": trade.notification_sent,
    }


async def tool_get_open_positions(limit: int = 20, session: AsyncSession = None) -> list[dict]:
    """Return recent simulated trades (all positions are open — no exit in simulation).

    Returns the most recent `limit` trades as open positions.
    """
    limit = min(max(1, limit), 100)
    result = await session.execute(
        select(Trade).order_by(Trade.created_at.desc()).limit(limit)
    )
    trades = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "instrument": t.instrument,
            "strike": t.strike,
            "option_type": t.option_type,
            "side": t.side,
            "entry_price": t.entry_price,
            "pnl": t.pnl,
            "signal_reason": t.signal_reason,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in trades
    ]


async def tool_get_pnl_summary(session: AsyncSession) -> dict:
    """Return overall simulated P&L statistics across all trades."""
    result = await session.execute(
        select(
            func.count(Trade.id).label("total_trades"),
            func.coalesce(func.sum(Trade.pnl), 0).label("total_pnl"),
            func.coalesce(func.avg(Trade.pnl), 0).label("avg_pnl"),
            func.coalesce(func.max(Trade.pnl), 0).label("max_pnl"),
            func.coalesce(func.min(Trade.pnl), 0).label("min_pnl"),
        )
    )
    row = result.one()

    long_result = await session.execute(
        select(func.count(Trade.id)).where(Trade.side == "LONG")
    )
    short_result = await session.execute(
        select(func.count(Trade.id)).where(Trade.side == "SHORT")
    )
    ce_result = await session.execute(
        select(func.count(Trade.id)).where(Trade.option_type == "CE")
    )
    pe_result = await session.execute(
        select(func.count(Trade.id)).where(Trade.option_type == "PE")
    )

    return {
        "total_trades": row.total_trades,
        "total_pnl": round(float(row.total_pnl), 2),
        "avg_pnl": round(float(row.avg_pnl), 2),
        "max_pnl": round(float(row.max_pnl), 2),
        "min_pnl": round(float(row.min_pnl), 2),
        "long_trades": long_result.scalar_one(),
        "short_trades": short_result.scalar_one(),
        "ce_trades": ce_result.scalar_one(),
        "pe_trades": pe_result.scalar_one(),
    }


async def tool_get_spike_events(limit: int = 10, session: AsyncSession = None) -> list[dict]:
    """Return the most recent spike-triggered trade events with their signal details."""
    limit = min(max(1, limit), 100)
    result = await session.execute(
        select(Trade).order_by(Trade.created_at.desc()).limit(limit)
    )
    trades = result.scalars().all()
    return [
        {
            "trade_id": str(t.id),
            "instrument": t.instrument,
            "strike": t.strike,
            "option_type": t.option_type,
            "side": t.side,
            "signal_reason": t.signal_reason,
            "entry_price": t.entry_price,
            "spike_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in trades
    ]


async def tool_get_best_strike_accuracy(session: AsyncSession) -> dict:
    """Return the strike price that generated the highest total simulated P&L.

    'Accuracy' is measured by total P&L per strike across all trades at that strike.
    """
    result = await session.execute(
        select(
            Trade.strike,
            Trade.option_type,
            func.count(Trade.id).label("trade_count"),
            func.sum(Trade.pnl).label("total_pnl"),
            func.avg(Trade.pnl).label("avg_pnl"),
        )
        .group_by(Trade.strike, Trade.option_type)
        .order_by(func.sum(Trade.pnl).desc())
        .limit(5)
    )
    rows = result.all()

    if not rows:
        return {"message": "No trades available for strike analysis"}

    best = rows[0]
    return {
        "best_strike": best.strike,
        "option_type": best.option_type,
        "total_pnl": round(float(best.total_pnl or 0), 2),
        "avg_pnl": round(float(best.avg_pnl or 0), 2),
        "trade_count": best.trade_count,
        "top_strikes": [
            {
                "strike": r.strike,
                "option_type": r.option_type,
                "trade_count": r.trade_count,
                "total_pnl": round(float(r.total_pnl or 0), 2),
                "avg_pnl": round(float(r.avg_pnl or 0), 2),
            }
            for r in rows
        ],
    }


async def tool_generate_trade_chart(session: AsyncSession) -> dict:
    """Generate a text-based summary chart of recent trade history.

    Returns a structured data payload suitable for text rendering.
    Shows the last 20 trades with their direction, strike, and P&L.
    """
    result = await session.execute(
        select(Trade).order_by(Trade.created_at.desc()).limit(20)
    )
    trades = result.scalars().all()

    if not trades:
        return {"chart": "No trades to display", "total": 0}

    # Build ASCII-style bar representation
    lines = ["Recent Trade History (newest first):", "-" * 60]
    for t in trades:
        direction = "▲ LONG " if t.side == "LONG" else "▼ SHORT"
        pnl_indicator = f"+{t.pnl:.2f}" if t.pnl >= 0 else f"{t.pnl:.2f}"
        ts = t.created_at.strftime("%H:%M:%S") if t.created_at else "N/A"
        lines.append(
            f"{ts} | {direction} | {t.instrument} {t.strike} {t.option_type} "
            f"| Entry: {t.entry_price:.2f} | PnL: {pnl_indicator}"
        )
    lines.append("-" * 60)

    # Summary stats
    total_pnl = sum(t.pnl for t in trades)
    winners = sum(1 for t in trades if t.pnl > 0)
    lines.append(f"Shown: {len(trades)} trades | Win rate: {winners}/{len(trades)} | Net PnL: {total_pnl:.2f}")

    return {
        "chart": "\n".join(lines),
        "total_shown": len(trades),
        "net_pnl": round(total_pnl, 2),
        "win_rate": f"{winners}/{len(trades)}",
    }
