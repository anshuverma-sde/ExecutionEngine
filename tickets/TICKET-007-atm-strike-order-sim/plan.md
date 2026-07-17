# Plan: TICKET-007 — ATM Strike Calculation & Order Simulation

## Branch
```bash
git checkout -b feature/TICKET-007-atm-strike-order-sim
```

## Implementation Steps

### Step 1 — `app/features/trading/strike.py`
```python
import math

NIFTY_STRIKE_INCREMENT = 50

def calculate_atm_strike(spot: float) -> int:
    """
    Round spot price to nearest NIFTY option strike (50pt increment).
    Uses round-half-up convention at midpoints (e.g. 22425 → 22450).
    
    Standard Python round() uses banker's rounding (round-half-to-even),
    which is statistically unbiased but not the financial convention.
    We use floor(x/50 + 0.5) * 50 for explicit round-half-up.
    
    Examples:
        22432 → 22450  (448.64 → 449 × 50)
        22424 → 22400  (448.48 → 448 × 50)
        22425 → 22450  (448.50 → 449 × 50, round-half-up)
    """
    return int(math.floor(spot / NIFTY_STRIKE_INCREMENT + 0.5)) * NIFTY_STRIKE_INCREMENT


def simulate_premium(spot: float, strike: int, option_type: str) -> float:
    """
    Mock option premium using intrinsic value + time value approximation.
    
    For a real implementation, this would call DhanHQ option chain API.
    For simulation: premium = intrinsic + ~0.2% of spot (time value proxy).
    
    Produces realistic NIFTY option values (50-500 INR range for ATM).
    """
    if option_type == "CE":
        intrinsic = max(0.0, spot - strike)
    else:  # PE
        intrinsic = max(0.0, strike - spot)
    
    time_value = spot * 0.002  # 0.2% of spot
    return round(intrinsic + time_value, 2)
```

### Step 2 — `app/features/trading/service.py`
```python
import asyncio
import logging
from uuid import uuid4
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.external.postgres.models import Trade
from app.features.spike_detection.schemas import Signal
from app.features.trading.strike import calculate_atm_strike, simulate_premium

logger = logging.getLogger(__name__)


async def handle_signal(signal: Signal, db: AsyncSession) -> Trade | None:
    """
    Convert a spike signal into a simulated trade.
    Persists to PostgreSQL in a transaction.
    Enqueues Celery notification after successful commit.
    """
    try:
        strike = calculate_atm_strike(signal.current_price)
        option_type = "CE" if signal.direction == "LONG" else "PE"
        premium = simulate_premium(signal.current_price, strike, option_type)

        trade = Trade(
            id=uuid4(),
            instrument="NIFTY",
            strike=strike,
            option_type=option_type,
            side=signal.direction,
            entry_price=premium,
            pnl=0.0,
            signal_reason=signal.reason,
            created_at=signal.ts,
            notification_sent=False,
        )

        async with db.begin():
            db.add(trade)

        logger.info(
            f"Trade committed: {trade.side} NIFTY {trade.strike} {trade.option_type} "
            f"@ {trade.entry_price} | {signal.reason}"
        )

        # Enqueue notification AFTER successful commit
        _enqueue_notification(str(trade.id))

        return trade

    except Exception as e:
        logger.error(f"Failed to handle signal: {e}")
        return None


def _enqueue_notification(trade_id: str):
    """Enqueue Celery task. Catches broker errors to prevent cascading failures."""
    try:
        from app.features.notifications.tasks import send_trade_notification
        send_trade_notification.delay(trade_id)
        logger.info(f"Notification enqueued for trade {trade_id}")
    except Exception as e:
        logger.error(
            f"Failed to enqueue notification for {trade_id}: {e}. "
            "Reconciliation will pick this up."
        )
```

### Step 3 — `app/features/trading/repository.py`
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.external.postgres.models import Trade


async def get_recent_trades(db: AsyncSession, limit: int = 20) -> list[Trade]:
    result = await db.execute(
        select(Trade).order_by(Trade.created_at.desc()).limit(limit)
    )
    return result.scalars().all()
```

### Step 4 — Wire Signal Handler into Pipeline
In `app/features/ingestion/pipeline.py`:
```python
from app.features.trading.service import handle_signal as _handle_signal_impl

_signal_handler = None
_db_session_factory = None

def register_signal_handler(handler, session_factory):
    global _signal_handler, _db_session_factory
    _signal_handler = handler
    _db_session_factory = session_factory

async def ingest_tick(security_id: str, ltp: float, ts: datetime):
    t_start = time.perf_counter()
    await _price_window.append(security_id, ltp, ts)
    signal = await _spike_detector.detect(security_id, ltp, ts)
    latency_ms = (time.perf_counter() - t_start) * 1000
    latency_collector.record(latency_ms)

    if signal and _signal_handler:
        # Run in background — do NOT await (keeps tick-to-signal path clean)
        asyncio.create_task(_dispatch_signal(signal))

    return signal

async def _dispatch_signal(signal):
    async with _db_session_factory() as db:
        await _signal_handler(signal, db)
```

In `app/main.py` lifespan:
```python
from app.features.ingestion.pipeline import register_signal_handler
from app.features.trading.service import handle_signal
from app.external.postgres.engine import AsyncSessionLocal

register_signal_handler(handle_signal, AsyncSessionLocal)
```

### Step 5 — `app/features/trading/router.py` — `GET /trades` Endpoint (bonus)
```python
@router.get("/trades")
async def list_trades(
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Trade).order_by(Trade.created_at.desc()).limit(limit)
    )
    trades = result.scalars().all()
    return [trade_to_dict(t) for t in trades]
```

## Verification
```python
# Unit test the strike calculation
assert calculate_atm_strike(22432) == 22450
assert calculate_atm_strike(22424) == 22400
assert calculate_atm_strike(22425) == 22450  # round-half-up
assert calculate_atm_strike(22400) == 22400  # exact multiple
assert calculate_atm_strike(22450) == 22450  # exact multiple
assert calculate_atm_strike(22449) == 22450  # rounds up
assert calculate_atm_strike(22401) == 22400  # rounds down
```

## Commit Message
```
feat: add ATM strike calculation (round-half-up), order simulation, and DB persistence
```
