"""Groq LLM provider (OpenAI-compatible, free tier).

Uses the `groq` Python SDK with the async client.
Supports parallel tool calling via the standard OpenAI function-calling format.

Recommended models (as of 2025):
  - llama-3.3-70b-versatile   (default — best for tool use)
  - llama-3.1-8b-instant      (fastest, lower quality)
  - mixtral-8x7b-32768        (good context window)

Get a free API key at: https://console.groq.com
"""
import json
import logging
from typing import Any

from app.external.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

MAX_TOKENS = 4096
MAX_TURNS = 10
TEMPERATURE = 0.0


class GroqProvider(BaseLLMProvider):
    """Groq LLM provider — OpenAI-compatible API with free tier."""

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._client: Any | None = None

    @property
    def model_name(self) -> str:
        return self._model

    async def initialise(self) -> None:
        from groq import AsyncGroq
        self._client = AsyncGroq(api_key=self._api_key)
        logger.info("GroqProvider initialised | model=%s", self._model)

    async def answer(
        self,
        question: str,
        tools: list[dict],
        tool_dispatcher: Any,
        session: Any = None,
    ) -> tuple[str, int]:
        if self._client is None:
            raise RuntimeError("GroqProvider.initialise() was not called")

        messages: list[dict] = [
            {
                "role": "system",
                "content": (
                    "You are an AI assistant for the Instant Strike Execution Engine, "
                    "a low-latency NIFTY 50 options trading system. "
                    "Use the available tools to retrieve live data before answering. "
                    "Be concise, precise, and cite specific numbers when available."
                ),
            },
            {"role": "user", "content": question},
        ]
        turn_count = 0

        while turn_count < MAX_TURNS:
            turn_count += 1
            logger.debug("Groq agentic turn %d", turn_count)

            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
            )

            choice = response.choices[0]
            msg = choice.message

            # Append assistant message to history
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in (msg.tool_calls or [])
                ] or None,
            })

            if not msg.tool_calls:
                logger.info("Groq agentic loop done | turns=%d", turn_count)
                return msg.content or "(no answer)", turn_count

            for tc in msg.tool_calls:
                try:
                    inputs = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    inputs = {}
                logger.info("Tool call: %s(%s)", tc.function.name, inputs)
                try:
                    result = await tool_dispatcher.dispatch(tc.function.name, inputs, session=session)
                    content = json.dumps(result, default=str)
                except Exception as exc:
                    logger.error("Tool %s failed: %s", tc.function.name, exc)
                    content = json.dumps({"error": str(exc)})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

        logger.warning("Groq: MAX_TURNS=%d reached", MAX_TURNS)
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                return msg["content"], turn_count
        return "(max turns reached)", turn_count

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("GroqProvider closed")
