# Plan: TICKET-005 — Spike Detector

## Branch
```bash
git checkout -b feature/TICKET-005-spike-detector
```

## Implementation Steps

### Step 1 — `app/features/spike_detection/schemas.py`
```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

@dataclass
class Signal:
    security_id: str
    direction: Literal["LONG", "SHORT"]
    current_price: float
    reference_price: float
    pct_change: float          # e.g. 5.23 (not 0.0523)
    ts: datetime
    reason: str                # e.g. "+5.23% spike in 60s"
```

### Step 2 — `app/features/spike_detection/detector.py`
```python
import logging
from datetime import datetime
from typing import Optional

import redis.asyncio as aioredis

from app.features.spike_detection.schemas import Signal
from app.external.redis.window import PriceWindow

logger = logging.getLogger(__name__)

SPIKE_THRESHOLD = 0.05          # 5%
COOLDOWN_SECONDS = 60           # prevent signal storm
COOLDOWN_KEY = "last_signal:{security_id}"


class SpikeDetector:
    def __init__(self, price_window: PriceWindow):
        self.price_window = price_window
        self._redis = price_window.redis

    async def detect(
        self, security_id: str, ltp: float, ts: datetime
    ) -> Optional[Signal]:
        # 1. Fetch reference price
        p_t60 = await self.price_window.get_price_at_t_minus_60(security_id, ts)
        if p_t60 is None:
            return None  # insufficient history (cold start)
        if p_t60 == 0:
            return None  # guard division by zero

        # 2. Compute return
        pct_change = (ltp - p_t60) / p_t60  # e.g. 0.0523

        # 3. Threshold check
        if pct_change >= SPIKE_THRESHOLD:
            direction = "LONG"
        elif pct_change <= -SPIKE_THRESHOLD:
            direction = "SHORT"
        else:
            return None

        # 4. Cooldown check
        cooldown_key = COOLDOWN_KEY.format(security_id=security_id)
        existing = await self._redis.get(cooldown_key)
        if existing:
            logger.debug(f"Signal suppressed by cooldown for {security_id}")
            return None

        # 5. Set cooldown
        await self._redis.setex(cooldown_key, COOLDOWN_SECONDS, "1")

        # 6. Build signal
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
        logger.info(f"SIGNAL: {direction} {security_id} @ {ltp} | {reason}")
        return signal
```

### Step 3 — Wire into Pipeline
In `app/features/ingestion/pipeline.py`, `ingest_tick()` already calls `_spike_detector.detect()` (from TICKET-004). The signal returned is then passed to `handle_signal()` from TICKET-007:

```python
async def ingest_tick(security_id: str, ltp: float, ts: datetime):
    t_start = time.perf_counter()
    await _price_window.append(security_id, ltp, ts)
    signal = await _spike_detector.detect(security_id, ltp, ts)
    latency_ms = (time.perf_counter() - t_start) * 1000
    latency_collector.record(latency_ms)

    if signal and _signal_handler:
        # Non-blocking: handle in background to not block ingestion path
        asyncio.create_task(_signal_handler(signal))

    return signal
```

The signal handler (`handle_signal`) is registered from TICKET-007 to keep the pipeline decoupled.

## Testing Scenarios

### Scenario A: Cold start (< 60s history)
- Append 10 ticks → `detect()` returns `None`

### Scenario B: 5% spike
- Append ticks at price 22000 for 60s
- Send tick at price 23100 → `(23100 - 22000) / 22000 = 5%` → LONG signal

### Scenario C: Cooldown
- Trigger LONG signal
- Send another 5% spike within 60s → `None` (cooldown active)

### Scenario D: Negative spike
- Append ticks at price 23000
- Send tick at 21850 → `(21850 - 23000) / 23000 = -5%` → SHORT signal

## Commit Message
```
feat: implement spike detector with 5% threshold and 60s cooldown
```
