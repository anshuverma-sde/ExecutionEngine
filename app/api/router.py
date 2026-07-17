"""
API router — aggregates all feature routers into a single APIRouter.

This module contains routing only. No business logic lives here.
"""
from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.api.routes.replay import router as replay_router
from app.api.routes.metrics import router as metrics_router
from app.features.trading.router import router as trading_router
from app.features.ai.router import router as ai_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(replay_router)
api_router.include_router(metrics_router)
api_router.include_router(trading_router, prefix="/trades")
api_router.include_router(ai_router)
