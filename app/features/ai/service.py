"""AI service: orchestrates the agentic loop and tool dispatch."""
import logging
from typing import Any

from app.features.ai.schemas import AskRequest, AskResponse

logger = logging.getLogger(__name__)


class AIService:
    """Dispatches natural-language questions to Claude via the agentic loop."""

    def __init__(self, anthropic_client: Any, mcp_server: Any) -> None:
        self._client = anthropic_client
        self._mcp = mcp_server

    async def answer_question(self, request: AskRequest) -> AskResponse:
        """
        Run the agentic loop for the given question and return a structured response.

        The model may invoke MCP tools multiple times before returning a final answer.
        """
        pass
