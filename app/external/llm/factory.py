"""LLM provider factory — selects and instantiates the correct provider from config.

To add a new provider:
  1. Implement BaseLLMProvider in app/external/llm/providers/<name>.py
  2. Add a case in create_llm_provider() below
  3. Add the matching env vars to app/core/config.py and .env.example

Supported providers (set LLM_PROVIDER in .env):
  groq      — Groq Cloud (free tier, llama-3.3-70b-versatile)
  openai    — OpenAI (GPT-4o, GPT-4o-mini, etc.)
  ollama    — Local Ollama instance (zero cost, no API key)
  langchain — LangGraph ReAct agent (set LANGCHAIN_BACKEND=groq|openai)
"""
import logging

from app.external.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


def create_llm_provider(
    provider: str,
    api_key: str = "",
    model: str = "",
    base_url: str = "",
    langchain_backend: str = "groq",
) -> BaseLLMProvider:
    """Instantiate the configured LLM provider.

    Args:
        provider:           One of "groq", "openai", "ollama", "langchain".
        api_key:            API key (not needed for Ollama).
        model:              Model identifier string.
        base_url:           Base URL override (used by Ollama; defaults to localhost:11434).
        langchain_backend:  Backend for the LangChain provider: "groq" or "openai".

    Returns:
        A concrete BaseLLMProvider instance (not yet initialised — call .initialise()).

    Raises:
        ValueError: If `provider` is not a recognised value.
    """
    p = provider.lower().strip()

    if p == "groq":
        from app.external.llm.providers.groq import GroqProvider
        resolved_model = model or "openai/gpt-oss-20b"   # fast OSS model on Groq, tool calling supported
        logger.info("LLM factory: Groq | model=%s", resolved_model)
        return GroqProvider(api_key=api_key, model=resolved_model)

    elif p == "openai":
        from app.external.llm.providers.openai import OpenAIProvider
        resolved_model = model or "gpt-5.4-mini"   # cost-optimised OpenAI model in 2026
        logger.info("LLM factory: OpenAI | model=%s", resolved_model)
        return OpenAIProvider(api_key=api_key, model=resolved_model)

    elif p == "ollama":
        from app.external.llm.providers.ollama import OllamaProvider
        resolved_url = base_url or "http://localhost:11434"
        resolved_model = model or "qwen3:8b"   # best local tool-caller in 2026
        logger.info("LLM factory: Ollama | model=%s | url=%s", resolved_model, resolved_url)
        return OllamaProvider(base_url=resolved_url, model=resolved_model)

    elif p == "langchain":
        from app.external.llm.providers.langchain import LangChainProvider
        backend = langchain_backend.lower().strip()
        resolved_model = model or ("openai/gpt-oss-20b" if backend == "groq" else "gpt-5.4-mini")
        logger.info("LLM factory: LangChain | backend=%s | model=%s", backend, resolved_model)
        return LangChainProvider(
            backend=backend,
            api_key=api_key,
            model=resolved_model,
            base_url=base_url,
        )

    else:
        raise ValueError(
            f"Unknown LLM provider: {provider!r}. "
            "Supported: 'groq', 'openai', 'ollama', 'langchain'"
        )
