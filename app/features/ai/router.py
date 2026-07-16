"""API router for the AI feature: POST /ask."""
import logging

from fastapi import APIRouter

from app.features.ai.schemas import AskRequest, AskResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai"])


@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    """Submit a natural-language question about trades, spikes, or system health."""
    pass
