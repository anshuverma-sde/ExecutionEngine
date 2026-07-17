"""API router for the trading feature."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.features.trading.schemas import TradeListResponse, TradeResponse
from app.features.trading.service import TradingService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["trading"])


@router.get("", response_model=TradeListResponse)
async def list_trades(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> TradeListResponse:
    """Return a paginated list of all recorded trades (newest first)."""
    svc = TradingService(db)
    trades, total = await svc.list_trades(page=page, page_size=page_size)
    return TradeListResponse(
        items=[TradeResponse.model_validate(t) for t in trades],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(
    trade_id: str,
    db: AsyncSession = Depends(get_db),
) -> TradeResponse:
    """Return a single trade by its UUID."""
    svc = TradingService(db)
    trade = await svc.get_trade(trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id!r} not found")
    return TradeResponse.model_validate(trade)
