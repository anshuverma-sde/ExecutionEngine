"""DhanHQ WebSocket consumer with reconnect logic and watchdog."""
import logging
from collections.abc import Callable, Awaitable

logger = logging.getLogger(__name__)


class DhanFeedConsumer:
    """
    Consumes the DhanHQ market data WebSocket feed.

    Handles reconnection with exponential backoff and a watchdog timer
    that restarts the connection if no tick is received within the timeout.
    """

    def __init__(
        self,
        client_id: str,
        access_token: str,
        on_tick: Callable[[dict], Awaitable[None]],
    ) -> None:
        self.client_id = client_id
        self.access_token = access_token
        self.on_tick = on_tick
        self.state: str = "stopped"
        self._reconnect_attempts: int = 0

    async def start(self) -> None:
        """Start the WebSocket consumer loop with reconnect logic."""
        pass

    async def stop(self) -> None:
        """Gracefully stop the consumer."""
        pass

    async def _connect(self) -> None:
        """Establish WebSocket connection to DhanHQ feed."""
        pass

    async def _handle_message(self, raw: dict) -> None:
        """Parse and dispatch an incoming feed message."""
        pass

    async def _watchdog(self) -> None:
        """Restart the connection if no tick is received within timeout."""
        pass
