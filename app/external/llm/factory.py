"""LLM provider factory — selects and instantiates the correct provider from config.

To add a new provider:
  1. Implement BaseLLMProvider in app/external/llm/<name>.py
  2. Add a case in create_llm_provider() below
  3. Add the matching env vars to app/core/config.py and .env.example

Supported providers (set LLM_PROVIDER in .env):
  groq    — Groq Cloud (free tier, llama-3.3-70b-versatile)
  openai  — OpenAI (GPT-4o, GPT-4o-mini, etc.)
  ollama  — Local Ollama instance (zero cost, no API key)
"""
import logging

from app.external.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


def create_llm_provider(
    provider: str,
    api_key: str = "",
    model: str = "",
    base_url: str = "",
) -> BaseLLMProvider:
    """Instantiate the configured LLM provider.

    Args:
        provider: One of "groq", "openai", "ollama".
        api_key:  API key (not needed for Ollama).
        model:    Model identifier string.
        base_url: Base URL override (used by Ollama; defaults to localhost:11434).

    Returns:
        A concrete BaseLLMProvider instance (not yet initialised — call .initialise()).

    Raises:
        ValueError: If `provider` is not a recognised value.
    """
    p = provider.lower().strip()

    if p == "groq":
        from app.external.llm.groq import GroqProvider
        resolved_model = model or "llama-3.3-70b-versatile"
        logger.info("LLM factory: Groq | model=%s", resolved_model)
        return GroqProvider(api_key=api_key, model=resolved_model)

    elif p == "openai":
        from app.external.llm.openai import OpenAIProvider
        resolved_model = model or "gpt-4o-mini"
        logger.info("LLM factory: OpenAI | model=%s", resolved_model)
        return OpenAIProvider(api_key=api_key, model=resolved_model)

    elif p == "ollama":
        from app.external.llm.ollama import OllamaProvider
        resolved_url = base_url or "http://localhost:11434"
        resolved_model = model or "llama3.2"
        logger.info("LLM factory: Ollama | model=%s | url=%s", resolved_model, resolved_url)
        return OllamaProvider(base_url=resolved_url, model=resolved_model)

    else:
        raise ValueError(
            f"Unknown LLM provider: {provider!r}. "
            "Supported: 'groq', 'openai', 'ollama'"
        )
