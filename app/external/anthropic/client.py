"""AsyncAnthropic client wrapper with agentic tool-use loop.

The agentic loop:
  1. Send user question + tool schemas to Claude.
  2. If the model responds with tool_use blocks, dispatch each tool via MCPServer.
  3. Feed tool results back as tool_result blocks in the next turn.
  4. Repeat until the model emits a text-only response (no more tool calls).
  5. Return the final text answer.

Max turns: configurable via MAX_TURNS (default 10) to prevent runaway loops.
"""
import json
import logging
from typing import Any

from app.external.anthropic import config as cfg

logger = logging.getLogger(__name__)


class AnthropicClient:
    """Wrapper around the AsyncAnthropic SDK supporting multi-turn tool use."""

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._client: Any | None = None

    async def initialise(self) -> None:
        """Create the underlying AsyncAnthropic SDK client."""
        import anthropic  # lazy import — avoids startup crash if not installed

        self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        logger.info("AnthropicClient initialised | model=%s", self._model)

    async def answer(
        self,
        question: str,
        tools: list[dict],
        tool_dispatcher: Any,  # MCPServer instance
        session: Any = None,   # AsyncSession for DB-backed tools
    ) -> tuple[str, int]:
        """Run the agentic loop and return (final_answer, turn_count).

        Args:
            question:        Natural-language question from the user.
            tools:           List of tool schemas in Anthropic format.
            tool_dispatcher: Object with .dispatch(tool_name, inputs, session).
            session:         Async DB session forwarded to tool dispatcher.

        Returns:
            Tuple of (answer_text, number_of_turns).
        """
        if self._client is None:
            raise RuntimeError("AnthropicClient.initialise() was not called")

        messages: list[dict] = [{"role": "user", "content": question}]
        turn_count = 0

        system_prompt = (
            "You are an AI assistant for the Instant Strike Execution Engine, "
            "a low-latency NIFTY 50 options trading system. "
            "Use the available tools to retrieve live data before answering. "
            "Be concise, precise, and cite specific numbers when available."
        )

        while turn_count < cfg.MAX_TURNS:
            turn_count += 1
            logger.debug("Agentic loop turn %d | messages=%d", turn_count, len(messages))

            response = await self._client.messages.create(
                model=self._model,
                max_tokens=cfg.MAX_TOKENS,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )

            # Collect all content blocks from the response
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            # Check stop reason
            if response.stop_reason == "end_turn":
                # Extract the final text answer
                text_blocks = [b for b in assistant_content if b.type == "text"]
                answer = text_blocks[-1].text if text_blocks else "(no answer)"
                logger.info("Agentic loop complete | turns=%d", turn_count)
                return answer, turn_count

            if response.stop_reason != "tool_use":
                # Unexpected stop — return whatever text we have
                text_blocks = [b for b in assistant_content if b.type == "text"]
                answer = text_blocks[-1].text if text_blocks else "(unexpected stop)"
                logger.warning("Unexpected stop_reason=%s", response.stop_reason)
                return answer, turn_count

            # Process tool_use blocks
            tool_results = []
            for block in assistant_content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_inputs = block.input
                tool_use_id = block.id

                logger.info("Tool call: %s(%s)", tool_name, tool_inputs)

                try:
                    result = await tool_dispatcher.dispatch(
                        tool_name, tool_inputs, session=session
                    )
                    result_content = json.dumps(result, default=str)
                    is_error = False
                except Exception as exc:
                    logger.error("Tool %s failed: %s", tool_name, exc)
                    result_content = json.dumps({"error": str(exc)})
                    is_error = True

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result_content,
                    "is_error": is_error,
                })

            messages.append({"role": "user", "content": tool_results})

        # Max turns reached — return the last text block seen
        logger.warning("Agentic loop hit MAX_TURNS=%d without end_turn", cfg.MAX_TURNS)
        for msg in reversed(messages):
            if msg["role"] == "assistant":
                content = msg["content"]
                if isinstance(content, list):
                    text_blocks = [b for b in content if hasattr(b, "type") and b.type == "text"]
                    if text_blocks:
                        return text_blocks[-1].text, turn_count
        return "(max turns reached — no answer generated)", turn_count

    async def close(self) -> None:
        """Release the underlying client resources."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("AnthropicClient closed")
