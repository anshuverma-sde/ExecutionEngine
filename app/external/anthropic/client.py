"""Groq LLM client with agentic tool-use loop (OpenAI-compatible API).

The spec allows any LLM provider (OpenAI, Ollama, LangChain, etc.).
Groq is used here because it offers a free tier with high-speed inference
on Llama 3.3 70B, which supports parallel tool calling.

Agentic loop:
  1. Send user question + tool schemas to the model.
  2. If the model returns tool_calls, dispatch each via MCPServer.
  3. Append tool results as role="tool" messages and repeat.
  4. Return the final text answer when no more tool_calls are returned.

Max turns: MAX_TURNS (default 10) prevents runaway loops.
"""
import json
import logging
from typing import Any

from app.external.anthropic import config as cfg

logger = logging.getLogger(__name__)


class AnthropicClient:
    """Groq LLM client with multi-turn tool-use loop.

    Named AnthropicClient for interface compatibility with the rest of the
    codebase (dependency injection in main.py and dependencies.py).
    """

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._client: Any | None = None

    async def initialise(self) -> None:
        """Create the underlying Groq async client."""
        from groq import AsyncGroq

        self._client = AsyncGroq(api_key=self._api_key)
        logger.info("GroqClient initialised | model=%s", self._model)

    async def answer(
        self,
        question: str,
        tools: list[dict],
        tool_dispatcher: Any,
        session: Any = None,
    ) -> tuple[str, int]:
        """Run the agentic tool-use loop and return (final_answer, turn_count).

        Args:
            question:        Natural-language question from the user.
            tools:           Tool schemas in OpenAI function-calling format.
            tool_dispatcher: MCPServer with .dispatch(tool_name, inputs, session).
            session:         Async DB session forwarded to DB-backed tools.

        Returns:
            Tuple of (answer_text, number_of_turns).
        """
        if self._client is None:
            raise RuntimeError("GroqClient.initialise() was not called")

        system_prompt = (
            "You are an AI assistant for the Instant Strike Execution Engine, "
            "a low-latency NIFTY 50 options trading system. "
            "Use the available tools to retrieve live data before answering. "
            "Be concise, precise, and cite specific numbers when available."
        )

        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]
        turn_count = 0

        while turn_count < cfg.MAX_TURNS:
            turn_count += 1
            logger.debug("Agentic loop turn %d | messages=%d", turn_count, len(messages))

            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=cfg.MAX_TOKENS,
                temperature=cfg.TEMPERATURE,
            )

            choice = response.choices[0]
            assistant_message = choice.message

            # Append assistant turn to history
            messages.append({
                "role": "assistant",
                "content": assistant_message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in (assistant_message.tool_calls or [])
                ] or None,
            })

            # No tool calls — final answer
            if not assistant_message.tool_calls:
                answer = assistant_message.content or "(no answer)"
                logger.info("Agentic loop complete | turns=%d", turn_count)
                return answer, turn_count

            # Process tool calls
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_inputs = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    tool_inputs = {}

                logger.info("Tool call: %s(%s)", tool_name, tool_inputs)

                try:
                    result = await tool_dispatcher.dispatch(
                        tool_name, tool_inputs, session=session
                    )
                    result_content = json.dumps(result, default=str)
                except Exception as exc:
                    logger.error("Tool %s failed: %s", tool_name, exc)
                    result_content = json.dumps({"error": str(exc)})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_content,
                })

        logger.warning("Agentic loop hit MAX_TURNS=%d", cfg.MAX_TURNS)
        # Return last assistant text seen
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                return msg["content"], turn_count
        return "(max turns reached — no answer generated)", turn_count

    async def close(self) -> None:
        """Release client resources."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("GroqClient closed")
