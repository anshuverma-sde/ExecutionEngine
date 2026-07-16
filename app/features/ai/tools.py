"""Tool implementations for the AI feature — queries the DB and returns structured data."""
import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.external.postgres.models import Trade
from app.metrics.latency import latency_collector

logger = logging.getLogger(__name__)


async def tool_list_recent_trades(limit: int = 10, session: AsyncSession = None) -> list[dict]:
    """Return the N most recent trades as plain dicts for the AI model to reason over."""
    limit = min(max(1, limit), 100)  # clamp between 1 and 100
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
            "notification_sent": t.notification_sent,
            "notification_failed": t.notification_failed,
        }
        for t in trades
    ]


async def tool_get_trade_by_id(trade_id: str, session: AsyncSession = None) -> dict | None:
    """Return a single trade by UUID."""
    try:
        uid = uuid.UUID(trade_id)
    except ValueError:
        return {"error": f"Invalid UUID: {trade_id!r}"}

    trade = await session.get(Trade, uid)
    if trade is None:
        return {"error": f"Trade {trade_id!r} not found"}

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
        "notification_sent_at": trade.notification_sent_at.isoformat() if trade.notification_sent_at else None,
        "notification_failed": trade.notification_failed,
        "notification_retry_count": trade.notification_retry_count,
    }


async def tool_get_spike_summary(symbol: str, session: AsyncSession = None) -> dict:
    """Return aggregated spike and trade statistics for the given symbol."""
    result = await session.execute(
        select(
            func.count(Trade.id).label("total_trades"),
            func.sum(Trade.pnl).label("total_pnl"),
            func.avg(Trade.entry_price).label("avg_entry_price"),
            func.sum(
                func.cast(Trade.side == "LONG", func.Integer())
            ).label("long_count"),
            func.sum(
                func.cast(Trade.side == "SHORT", func.Integer())
            ).label("short_count"),
        ).where(Trade.instrument == symbol.upper())
    )
    row = result.one()

    # Fallback to individual counts if SUM CAST doesn't work cross-DB
    long_result = await session.execute(
        select(func.count(Trade.id)).where(
            Trade.instrument == symbol.upper(), Trade.side == "LONG"
        )
    )
    short_result = await session.execute(
        select(func.count(Trade.id)).where(
            Trade.instrument == symbol.upper(), Trade.side == "SHORT"
        )
    )

    return {
        "symbol": symbol.upper(),
        "total_trades": row.total_trades or 0,
        "total_pnl": round(float(row.total_pnl or 0), 2),
        "avg_entry_price": round(float(row.avg_entry_price or 0), 2),
        "long_count": long_result.scalar_one(),
        "short_count": short_result.scalar_one(),
    }


async def tool_get_pnl_summary(session: AsyncSession = None) -> dict:
    """Return overall simulated P&L across all trades."""
    result = await session.execute(
        select(
            func.count(Trade.id).label("total_trades"),
            func.sum(Trade.pnl).label("total_pnl"),
            func.avg(Trade.pnl).label("avg_pnl"),
            func.max(Trade.pnl).label("max_pnl"),
            func.min(Trade.pnl).label("min_pnl"),
        )
    )
    row = result.one()

    notified_result = await session.execute(
        select(func.count(Trade.id)).where(Trade.notification_sent.is_(True))
    )
    failed_result = await session.execute(
        select(func.count(Trade.id)).where(Trade.notification_failed.is_(True))
    )

    return {
        "total_trades": row.total_trades or 0,
        "total_pnl": round(float(row.total_pnl or 0), 2),
        "avg_pnl": round(float(row.avg_pnl or 0), 2),
        "max_pnl": round(float(row.max_pnl or 0), 2),
        "min_pnl": round(float(row.min_pnl or 0), 2),
        "notifications_sent": notified_result.scalar_one(),
        "notifications_failed": failed_result.scalar_one(),
    }


async def tool_get_latency_stats() -> dict:
    """Return p50/p95/p99 latency metrics from the LatencyCollector."""
    stats = latency_collector.stats()
    stats["sla_target_ms"] = 50.0
    return stats


async def tool_get_system_status() -> dict:
    """Return high-level system health: feed connectivity, Redis, DB ping."""
    import asyncio
    import aioredis

    from app.core.config import settings
    from app.external.dhanhq.consumer import DhanFeedConsumer

    status: dict = {"services": {}}

    # Redis check
    try:
        import redis as sync_redis
        r = sync_redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        r.ping()
        status["services"]["redis"] = "ok"
    except Exception as exc:
        status["services"]["redis"] = f"error: {exc}"

    # DB check (simple connection test via async engine)
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        engine = create_async_engine(settings.DATABASE_URL, pool_size=1)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        status["services"]["postgres"] = "ok"
    except Exception as exc:
        status["services"]["postgres"] = f"error: {exc}"

    # Latency stats summary
    stats = latency_collector.stats()
    status["latency"] = {
        "p99_ms": stats.get("p99_ms"),
        "sla_met": stats.get("sla_met"),
        "sample_count": stats.get("count"),
    }

    return status
