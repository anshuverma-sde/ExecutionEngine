"""Anthropic / Claude API configuration."""
from app.core.config import settings

ANTHROPIC_API_KEY: str = settings.ANTHROPIC_API_KEY
ANTHROPIC_MODEL: str = settings.ANTHROPIC_MODEL

# Agentic loop limits
MAX_TOKENS: int = 4096
MAX_TURNS: int = 10
TEMPERATURE: float = 0.0  # Deterministic for trading analysis
