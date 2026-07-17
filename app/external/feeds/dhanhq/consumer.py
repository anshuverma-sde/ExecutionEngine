"""DhanHQ WebSocket consumer — implements FeedConsumer.

Resilience design:
  - Exponential backoff reconnect: 1s → 2s → 4s → … → 60s cap
  - Watchdog task: logs WARNING after 30s of silence, reconnects after 5min
  - Malformed frames: caught in _handle_tick(), logged, processing continues
  - Exception in tick handler: never propagates to the consumer loop
  - Graceful shutdown: stop() cancels all tasks cleanly
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from app.external.feeds.base import FeedConsumer

logger = logging.getLogger(__name__)

SECURITY_ID = "13"          # NIFTY 50 on NSE
RECONNECT_BASE_S = 1        # Initial reconnect delay
RECONNECT_MAX_S = 60        # Maximum reconnect delay
WATCHDOG_WARN_S = 30        # Log WARNING after N seconds of silence
WATCHDOG_RECONNECT_S = 300  # Force reconnect after 5 minutes of silence


class DhanFeedConsumer(FeedConsumer):
    """
    Consumes the DhanHQ live market feed via WebSocket.

    Subscribes to NIFTY 50 LTP updates (Security ID 13, NSE).
    All incoming ticks are passed to on_tick(security_id, ltp, ts).
    """

    def __init__(
        self,
        client_id: str,
        access_token: str,
        on_tick: Callable[[str, float, datetime], Awaitable[None]],
    ) -> None:
        self.client_id = client_id
        self.access_token = access_token
        self._on_tick = on_tick

        self.state: str = "stopped"
        self._running: bool = False
        self._last_tick_time: float = 0.0
        self._reconnect_delay: float = RECONNECT_BASE_S
        self._watchdog_task: asyncio.Task | None = None
        self._force_reconnect: asyncio.Event = asyncio.Event()

    async def start(self) -> None:
        """Start the WebSocket consumer loop. Runs until stop() is called."""
        self._running = True
        self._watchdog_task = asyncio.create_task(self._watchdog())
        await self._connection_loop()

    async def stop(self) -> None:
        """Gracefully shut down the consumer and watchdog."""
        self._running = False
        self.state = "stopped"
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        logger.info("DhanHQ consumer stopped")

    async def _connection_loop(self) -> None:
        """Outer reconnect loop — keeps trying until stop() is called."""
        while self._running:
            try:
                self.state = "connecting"
                logger.info(
                    "Connecting to DhanHQ feed (backoff=%.0fs)", self._reconnect_delay
                )
                self._force_reconnect.clear()
                await self._connect()
                self._reconnect_delay = RECONNECT_BASE_S   # reset on clean exit

            except asyncio.CancelledError:
                break

            except Exception as exc:
                self.state = "reconnecting"
                logger.error(
                    "DhanHQ feed error: %s — reconnecting in %.0fs",
                    exc,
                    self._reconnect_delay,
                )

            if not self._running:
                break

            try:
                await asyncio.wait_for(
                    self._force_reconnect.wait(),
                    timeout=self._reconnect_delay,
                )
            except asyncio.TimeoutError:
                pass

            self._reconnect_delay = min(self._reconnect_delay * 2, RECONNECT_MAX_S)

    async def _connect(self) -> None:
        """Establish a single WebSocket session. Returns when the session ends."""
        try:
            from dhanhq import marketfeed
        except ImportError:
            logger.error("dhanhq package not installed — cannot connect to live feed")
            await asyncio.sleep(RECONNECT_MAX_S)
            return

        sub_type = getattr(marketfeed, "Ticker", getattr(marketfeed, "LTP", 15))
        instruments = [(marketfeed.NSE, SECURITY_ID, sub_type)]

        feed = marketfeed.DhanFeed(
            client_id=self.client_id,
            access_token=self.access_token,
            instruments=instruments,
            version="v2",
        )

        await feed.connect()

        self.state = "connected"
        self._reconnect_delay = RECONNECT_BASE_S
        logger.info("DhanHQ feed connected — subscribed to NIFTY 50 LTP (security_id=%s)", SECURITY_ID)

        # dhanhq v2 uses a polling model — call get_instrument_data() in a loop
        while True:
            tick_data = await feed.get_instrument_data()
            if tick_data:
                self._handle_tick(tick_data)

    def _handle_tick(self, tick_data: dict) -> None:
        """Process a single tick from the DhanHQ feed.

        Never raises — all errors are caught and logged.
        """
        try:
            ltp = float(
                tick_data.get("LTP")
                or tick_data.get("ltp")
                or tick_data.get("last_price")
                or 0
            )
            if ltp <= 0:
                return   # heartbeat or non-price message

            ts = datetime.now(timezone.utc)
            self._last_tick_time = ts.timestamp()

            asyncio.ensure_future(self._on_tick(SECURITY_ID, ltp, ts))

        except Exception as exc:
            logger.warning("Malformed tick skipped: %s | raw=%s", exc, tick_data)

    async def _watchdog(self) -> None:
        """Monitor feed liveness. Warn on silence, force-reconnect on long silence."""
        while self._running:
            await asyncio.sleep(10)

            if self._last_tick_time == 0:
                continue  # no tick received yet (startup)

            silence_s = asyncio.get_running_loop().time() - self._last_tick_time

            if silence_s >= WATCHDOG_RECONNECT_S:
                logger.error(
                    "Feed silent for %.0fs — forcing reconnect", silence_s
                )
                self._force_reconnect.set()

            elif silence_s >= WATCHDOG_WARN_S:
                logger.warning(
                    "Feed silent for %.0fs (market may be closed)", silence_s
                )
