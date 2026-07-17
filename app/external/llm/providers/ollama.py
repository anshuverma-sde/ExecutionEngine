"""Ollama LLM provider — local inference, zero cost, no API key needed.

Uses the OpenAI-compatible REST API that Ollama exposes at localhost:11434.
Set LLM_PROVIDER=ollama in your .env to activate.

Install Ollama: https://ollama.com
Pull a model: ollama pull llama3.2 (or qwen2.5, mistral, etc.)

Note: Tool calling support depends on the model. llama3.1+ and qwen2.5
support function calling reliably.
"""
import json
import logging
from typing import Any

from app.external.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

MAX_TOKENS = 4096
MAX_TURNS = 10
TEMPERATURE = 0.0


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider via OpenAI-compatible API."""

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client: Any | None = None

    @property
    def model_name(self) -> str:
        return self._model

    async def initialise(self) -> None:
        from openai import AsyncOpenAI
        # Ollama exposes an OpenAI-compatible API — no API key required
        self._client = AsyncOpenAI(
            api_key="ollama",
            base_url=f"{self._base_url}/v1",
        )
        logger.info("OllamaProvider initialised | model=%s | url=%s", self._model, self._base_url)

    async def answer(
        self,
        question: str,
        tools: list[dict],
        tool_dispatcher: Any,
        session: Any = None,
    ) -> tuple[str, int]:
        if self._client is None:
            raise RuntimeError("OllamaProvider.initialise() was not called")

        messages: list[dict] = [
            {
                "role": "system",
                "content": (
                    "You are an AI assistant for the Instant Strike Execution Engine, "
                    "a low-latency NIFTY 50 options trading system. "
                    "Use the available tools to retrieve live data before answering."
                ),
            },
            {"role": "user", "content": question},
        ]
        turn_count = 0

        while turn_count < MAX_TURNS:
            turn_count += 1
            logger.debug("Ollama agentic turn %d", turn_count)

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

            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in (msg.tool_calls or [])
                ] or None,
            })

            if not msg.tool_calls:
                logger.info("Ollama agentic loop done | turns=%d", turn_count)
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

        logger.warning("Ollama: MAX_TURNS=%d reached", MAX_TURNS)
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                return msg["content"], turn_count
        return "(max turns reached)", turn_count

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("OllamaProvider closed")
