"""API router for the trading feature: GET /trades, GET /trades/{id}."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.features.trading.schemas import TradeListResponse, TradeResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["trading"])


@router.get("", response_model=TradeListResponse)
async def list_trades(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> TradeListResponse:
    """Return a paginated list of all recorded trades."""
    pass


@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(
    trade_id: str,
    db: AsyncSession = Depends(get_db),
) -> TradeResponse:
    """Return a single trade by its UUID."""
    pass
