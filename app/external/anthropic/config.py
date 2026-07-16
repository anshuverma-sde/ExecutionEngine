"""Groq AI configuration (replaces Anthropic — spec allows any LLM provider)."""
from app.core.config import settings

GROQ_API_KEY: str = settings.GROQ_API_KEY
GROQ_MODEL: str = settings.GROQ_MODEL

# Agentic loop limits
MAX_TOKENS: int = 4096
MAX_TURNS: int = 10
TEMPERATURE: float = 0.0  # Deterministic for trading analysis
