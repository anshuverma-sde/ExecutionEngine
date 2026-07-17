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

    The LLM (configured via LLM_PROVIDER env var: groq/openai/ollama) uses
    6 MCP tools to answer grounded in live data:
      get_last_trade, get_open_positions, get_pnl_summary,
      get_spike_events, get_best_strike_accuracy, generate_trade_chart

    Example questions:
    - "What was the last trade?"
    - "Show today's losing trades."
    - "Which strike performed best?"
    - "Compare CE vs PE profitability."
    """
    from app.core.dependencies import get_anthropic_client, get_mcp_server
    from app.features.ai.service import AIService

    anthropic_client = get_anthropic_client()
    mcp_server = get_mcp_server()

    service = AIService(anthropic_client=anthropic_client, mcp_server=mcp_server)
    return await service.answer_question(request, session=db)
