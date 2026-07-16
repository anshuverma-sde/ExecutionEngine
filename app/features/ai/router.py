"""API router for the AI feature: POST /ask."""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.features.ai.schemas import AskRequest, AskResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai"])


@router.post("/ask", response_model=AskResponse)
async def ask(
    request: AskRequest,
    db: AsyncSession = Depends(get_db),
) -> AskResponse:
    """Submit a natural-language question about trades, spikes, or system health.

    Claude uses up to 6 MCP tools (list_recent_trades, get_trade_by_id,
    get_spike_summary, get_pnl_summary, get_latency_stats, get_system_status)
    to answer grounded in live data.

    Example questions:
    - "What were the last 5 trades?"
    - "Is the p99 latency SLA being met?"
    - "What's the total P&L for NIFTY today?"
    - "Are there any notification delivery failures?"
    """
    from app.core.dependencies import get_anthropic_client, get_mcp_server
    from app.features.ai.service import AIService

    anthropic_client = get_anthropic_client()
    mcp_server = get_mcp_server()

    service = AIService(anthropic_client=anthropic_client, mcp_server=mcp_server)
    return await service.answer_question(request, session=db)
