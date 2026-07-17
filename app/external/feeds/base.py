"""Abstract protocol for market data feed consumers.

All feed implementations must satisfy this interface so the application
lifespan can start/stop any feed without knowing its concrete type.

To add a new broker (e.g., Zerodha, Upstox):
  1. Create app/external/feeds/<broker>/consumer.py
  2. Implement FeedConsumer
  3. Update the factory in app/external/feeds/factory.py
"""
from abc import ABC, abstractmethod


class FeedConsumer(ABC):
    """Abstract base for live market data feed consumers."""

    @abstractmethod
    async def start(self) -> None:
        """Connect to the feed and begin processing ticks. Blocks until stopped."""

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully disconnect and clean up all tasks."""
