"""Abstract base class for LLM providers.

All provider implementations must implement this interface so the rest
of the codebase is fully decoupled from any specific LLM vendor.

To add a new provider:
  1. Create app/external/llm/<provider>.py (e.g. openai.py, ollama.py)
  2. Subclass BaseLLMProvider and implement all abstract methods
  3. Register it in app/external/llm/factory.py
  4. Add the corresponding config key to app/core/config.py
"""
from abc import ABC, abstractmethod
from typing import Any


class BaseLLMProvider(ABC):
    """Protocol every LLM provider must satisfy."""

    @abstractmethod
    async def initialise(self) -> None:
        """Create underlying SDK client / warm connection pool."""

    @abstractmethod
    async def answer(
        self,
        question: str,
        tools: list[dict],
        tool_dispatcher: Any,
        session: Any = None,
    ) -> tuple[str, int]:
        """Run agentic loop and return (final_answer, turn_count).

        Args:
            question:        Natural-language question from the user.
            tools:           Tool schemas in the provider's expected format.
            tool_dispatcher: Object with .dispatch(tool_name, inputs, session).
            session:         Async DB session forwarded to DB-backed tools.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release SDK client and connection resources."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier string (for logging / response metadata)."""
