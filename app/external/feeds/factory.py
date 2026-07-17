"""Factory for creating FeedConsumer instances.

Add new brokers here without touching app/main.py.
"""
from collections.abc import Awaitable, Callable
from datetime import datetime

from app.external.feeds.base import FeedConsumer


def create_feed_consumer(
    provider: str,
    on_tick: Callable[[str, float, datetime], Awaitable[None]],
    **kwargs,
) -> FeedConsumer:
    """Return a FeedConsumer for the requested provider.

    Args:
        provider: Feed provider name — currently only "dhanhq".
        on_tick:  Async callback invoked for each incoming tick.
        **kwargs: Provider-specific config (e.g., client_id, access_token).

    Raises:
        ValueError: Unknown provider name.
    """
    if provider == "dhanhq":
        from app.external.feeds.dhanhq.consumer import DhanFeedConsumer
        return DhanFeedConsumer(on_tick=on_tick, **kwargs)

    raise ValueError(f"Unknown feed provider: {provider!r}. Supported: dhanhq")
