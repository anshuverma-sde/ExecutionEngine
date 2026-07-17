"""Spike detector: ±5% price change over 60 seconds triggers a trade signal.

Algorithm (per spec):
  On every tick with price Pt at time t:
    1. Fetch P(t-60) from Redis rolling window
    2. If P(t-60) is None → cold start (< 60s history) → skip
    3. pct_change = (Pt - P(t-60)) / P(t-60)
    4. If pct_change >= +0.05 → emit LONG signal
    5. If pct_change <= -0.05 → emit SHORT signal
    6. Otherwise → no signal

Cooldown:
  After a signal fires, a 60-second cooldown suppresses further signals for
  the same security. This prevents a signal storm during a sustained move.
  Implemented in CooldownManager using Redis SETNX.
"""
import logging
from datetime import datetime
from typing import Any

from app.features.spike_detection.cooldown import CooldownManager
from app.features.spike_detection.schemas import Signal

logger = logging.getLogger(__name__)

SPIKE_THRESHOLD = 0.05   # 5%


class SpikeDetector:
    """Detects ±5% price spikes over a 60-second rolling window.

    Depends on:
      - price_window : PriceWindow (app.external.redis.window)
      - cooldown     : CooldownManager (app.features.spike_detection.cooldown)
    """

    def __init__(self, price_window: Any) -> None:
        self._window = price_window
        self._cooldown = CooldownManager(price_window._redis)

    async def detect(
        self, security_id: str, ltp: float, ts: datetime
    ) -> Signal | None:
        """Run spike detection for a single tick.

        Returns a Signal if a spike is detected and not in cooldown, else None.
        """
        # 1. Fetch reference price (oldest tick in 60s window)
        p_t60 = await self._window.get_price_at_t_minus_60(security_id, ts)

        if p_t60 is None:
            return None   # cold start — not enough history yet

        if p_t60 == 0.0:
            return None   # guard against division by zero

        # 2. Compute 60-second return
        pct_change = (ltp - p_t60) / p_t60   # e.g. 0.0523

        # 3. Threshold check
        if pct_change >= SPIKE_THRESHOLD:
            direction = "LONG"
        elif pct_change <= -SPIKE_THRESHOLD:
            direction = "SHORT"
        else:
            return None   # within normal range

        # 4. Cooldown check — atomic SETNX prevents duplicate signals
        claimed = await self._cooldown.set_cooldown(security_id)
        if not claimed:
            logger.debug(
                "Signal suppressed by cooldown for %s (%.2f%%)",
                security_id,
                pct_change * 100,
            )
            return None

        # 5. Build and return signal
        pct_display = pct_change * 100
        sign = "+" if pct_display > 0 else ""
        reason = f"{sign}{pct_display:.2f}% spike in 60s"

        signal = Signal(
            security_id=security_id,
            direction=direction,
            current_price=ltp,
            reference_price=p_t60,
            pct_change=pct_display,
            ts=ts,
            reason=reason,
        )

        logger.info(
            "SIGNAL %s | security=%s | price=%.2f | ref=%.2f | %s",
            direction,
            security_id,
            ltp,
            p_t60,
            reason,
        )
        return signal
