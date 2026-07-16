"""AI service: orchestrates the agentic loop for trade intelligence queries."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.external.anthropic.client import AnthropicClient
from app.features.ai.mcp_server import MCPServer
from app.features.ai.schemas import AskRequest, AskResponse

logger = logging.getLogger(__name__)


class AIService:
    """Dispatches natural-language questions to Claude via the agentic tool-use loop."""

    def __init__(self, anthropic_client: AnthropicClient, mcp_server: MCPServer) -> None:
        self._client = anthropic_client
        self._mcp = mcp_server

    async def answer_question(
        self, request: AskRequest, session: AsyncSession
    ) -> AskResponse:
        """Run the agentic loop and return a structured response.

        The model may invoke MCP tools multiple times before producing a final answer.
        Tool results (trades, P&L, latency stats) are fed back as tool_result blocks.

        Args:
            request: AskRequest with the user's natural-language question.
            session: Async DB session forwarded to DB-backed tools.

        Returns:
            AskResponse with the final answer, model name, and turn count.
        """
        logger.info("AI query received: %q", request.question[:120])

        tools = self._mcp.get_tools()

        answer, turns = await self._client.answer(
            question=request.question,
            tools=tools,
            tool_dispatcher=self._mcp,
            session=session,
        )

        logger.info("AI query answered in %d turn(s)", turns)
        return AskResponse(
            answer=answer,
            model=self._client._model,
            turns=turns,
        )
