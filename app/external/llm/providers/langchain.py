"""LangChain/LangGraph agentic provider.

Uses LangGraph's `create_react_agent` to power the agentic loop.
Supports Groq and OpenAI backends via LangChain chat models.

Set in .env:
  LLM_PROVIDER=langchain
  LANGCHAIN_BACKEND=groq     # or openai
  GROQ_API_KEY=...           # reuses existing key
  GROQ_MODEL=llama-3.3-70b-versatile

Advantage over raw Groq/OpenAI providers:
  - LangGraph manages the ReAct loop, conversation state, and tool routing
  - Swapping backends (Groq ↔ OpenAI) requires only LANGCHAIN_BACKEND change
  - Ready for multi-agent graphs, memory, and streaming in future iterations
"""
import json
import logging
from typing import Any

from app.external.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an AI assistant for the Instant Strike Execution Engine, "
    "a low-latency NIFTY 50 options trading system. "
    "Use the available tools to retrieve live data before answering. "
    "Be concise, precise, and cite specific numbers when available."
)

MAX_TURNS = 10


def _build_langchain_tools(
    tool_schemas: list[dict],
    tool_dispatcher: Any,
    session: Any,
) -> list:
    """Convert OpenAI-format tool schemas + dispatcher into LangChain StructuredTool objects.

    Each tool schema is expected in the standard OpenAI function-calling format:
      {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}

    The returned StructuredTool instances delegate execution to `tool_dispatcher.dispatch()`.
    """
    from langchain_core.tools import StructuredTool

    lc_tools: list = []
    for schema in tool_schemas:
        fn_def = schema.get("function", schema)  # handle both wrapped and bare formats
        name = fn_def["name"]
        description = fn_def.get("description", "")
        parameters = fn_def.get("parameters", {"type": "object", "properties": {}})

        # Capture loop variables in closure
        def _make_async_func(tool_name: str):
            async def _tool_fn(**kwargs: Any) -> str:
                try:
                    result = await tool_dispatcher.dispatch(tool_name, kwargs, session=session)
                    return json.dumps(result, default=str)
                except Exception as exc:
                    logger.error("LangChain tool %s failed: %s", tool_name, exc)
                    return json.dumps({"error": str(exc)})
            _tool_fn.__name__ = tool_name
            return _tool_fn

        lc_tools.append(
            StructuredTool.from_function(
                coroutine=_make_async_func(name),
                name=name,
                description=description,
                args_schema=_json_schema_to_pydantic(name, parameters),
            )
        )

    return lc_tools


def _json_schema_to_pydantic(tool_name: str, schema: dict):
    """Build a minimal Pydantic v2 model from a JSON Schema dict for use as args_schema."""
    from pydantic import create_model

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    field_definitions: dict = {}
    for prop_name, prop_schema in properties.items():
        python_type = _json_type_to_python(prop_schema)
        if prop_name in required:
            field_definitions[prop_name] = (python_type, ...)
        else:
            from typing import Optional
            default = prop_schema.get("default", None)
            field_definitions[prop_name] = (Optional[python_type], default)

    model_name = f"{tool_name.title().replace('_', '')}Args"
    return create_model(model_name, **field_definitions)


def _json_type_to_python(prop_schema: dict):
    """Map a JSON Schema type string to a Python type."""
    json_type = prop_schema.get("type", "string")
    mapping = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    return mapping.get(json_type, str)


class LangChainProvider(BaseLLMProvider):
    """LangGraph ReAct agent provider — Groq or OpenAI backend.

    The LangGraph agent graph handles the full tool-call loop; this class
    only wires the backend model and converts tool schemas.
    """

    def __init__(
        self,
        backend: str,
        api_key: str,
        model: str,
        base_url: str = "",
    ) -> None:
        """
        Args:
            backend:  "groq" or "openai" — selects the LangChain chat model.
            api_key:  API key for the chosen backend.
            model:    Model identifier (e.g. "llama-3.3-70b-versatile").
            base_url: Unused for cloud backends; reserved for future local backends.
        """
        self._backend = backend.lower().strip()
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._llm: Any | None = None

    @property
    def model_name(self) -> str:
        return self._model

    async def initialise(self) -> None:
        if self._backend == "groq":
            from langchain_groq import ChatGroq
            self._llm = ChatGroq(
                api_key=self._api_key,
                model=self._model,
                temperature=0,
            )
            logger.info("LangChainProvider ready | backend=groq | model=%s", self._model)

        elif self._backend == "openai":
            from langchain_openai import ChatOpenAI
            self._llm = ChatOpenAI(
                api_key=self._api_key,
                model=self._model,
                temperature=0,
            )
            logger.info("LangChainProvider ready | backend=openai | model=%s", self._model)

        else:
            raise ValueError(
                f"Unknown LangChain backend: {self._backend!r}. Supported: 'groq', 'openai'"
            )

    async def answer(
        self,
        question: str,
        tools: list[dict],
        tool_dispatcher: Any,
        session: Any = None,
    ) -> tuple[str, int]:
        if self._llm is None:
            raise RuntimeError("LangChainProvider.initialise() was not called")

        from langgraph.prebuilt import create_react_agent
        from langchain_core.messages import SystemMessage, HumanMessage

        lc_tools = _build_langchain_tools(tools, tool_dispatcher, session)
        agent = create_react_agent(self._llm, lc_tools)

        result = await agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=question),
                ]
            }
        )

        messages = result.get("messages", [])
        # Count AI turns (each AI message = one LLM call)
        turn_count = sum(
            1 for m in messages if getattr(m, "type", None) == "ai"
        )

        # Last message is the final AI answer
        final_msg = messages[-1] if messages else None
        answer = (
            final_msg.content
            if final_msg and hasattr(final_msg, "content")
            else "(no answer)"
        )

        logger.info("LangChain agentic loop done | turns=%d", turn_count)
        return answer or "(no answer)", max(turn_count, 1)

    async def close(self) -> None:
        # LangChain chat models hold no persistent connections
        self._llm = None
        logger.info("LangChainProvider closed")
