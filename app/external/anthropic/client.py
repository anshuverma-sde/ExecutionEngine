"""AsyncAnthropic client wrapper with agentic loop support."""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class AnthropicClient:
    """
    Wrapper around the AsyncAnthropic SDK.

    Supports a multi-turn agentic loop where the model can invoke
    registered tools (MCP / function-calling) to answer trading queries.
    """

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model
        self._client: Any | None = None

    async def initialise(self) -> None:
        """Create the underlying AsyncAnthropic client."""
        pass

    async def answer(self, question: str, tools: list[dict]) -> str:
        """
        Run the agentic loop and return the final text answer.

        Args:
            question: Natural-language question from the user.
            tools: List of tool schemas available to the model.

        Returns:
            Final answer string after the agentic loop completes.
        """
        pass

    async def close(self) -> None:
        """Release the client resources."""
        pass
