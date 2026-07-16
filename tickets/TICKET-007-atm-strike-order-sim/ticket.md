# TICKET-007: ATM Strike Calculation & Order Simulation

**Branch:** `feature/TICKET-007-atm-strike-order-sim`  
**Priority:** P1 — Depends on TICKET-002 (DB), TICKET-005 (Signal)  
**Estimate:** ~1.5h

## Summary
Implement the quant logic: ATM strike selection (NIFTY 50pt increments) and order simulation. On a signal, calculate the strike, determine CE/PE, mock the entry premium, and persist the trade to PostgreSQL.

## ATM Strike Calculation

### NIFTY Option Chain Rules
- NIFTY options trade in 50-point increments (22400, 22450, 22500, ...)
- ATM = nearest 50-point multiple to the spot price

### Standard Rounding
```python
def calculate_atm_strike(spot: float) -> int:
    return round(spot / 50) * 50
```

### Spec Examples Verification
| Spot | Formula | ATM |
|---|---|---|
| 22432 | round(22432/50)*50 = round(448.64)*50 = 449*50 | **22450** ✓ |
| 22424 | round(22424/50)*50 = round(448.48)*50 = 448*50 | **22400** ✓ |
| 22425 | round(22425/50)*50 = round(448.50)*50 = ? | **Ambiguous** |

### The 22425 Decision (Spec intentional ambiguity)
`round(448.5)` in Python uses **banker's rounding** (round-half-to-even) → `448` → **22400**.

**Decision: Use 22450 (round-half-up) via `math.floor(spot/50 + 0.5) * 50`**

**Rationale:** In options markets, the convention is to round up at the midpoint because:
1. For a long signal (+5% spike), the higher strike is more conservative (less ITM risk)
2. Most market data providers and exchange specs use round-half-up for strike selection
3. Python's banker's rounding is a statistical artifact, not a financial convention

Document this in README under "Architecture Decisions."

### Implementation
```python
import math

def calculate_atm_strike(spot: float) -> int:
    """Round to nearest 50, with half-up convention at midpoints."""
    return int(math.floor(spot / 50 + 0.5)) * 50
```

## Order Simulation

### Logic
```
On LONG signal → buy ATM Call (CE)
On SHORT signal → buy ATM Put (PE)
```

### Premium Simulation
The spec says "fetch or mock the option premium." Decision: **mock with a simple model.**

Mock premium formula:
```python
def simulate_premium(spot: float, strike: int, option_type: str) -> float:
    """
    Simple intrinsic + time value approximation.
    For evaluation, a realistic mock is sufficient.
    """
    intrinsic = max(0, spot - strike) if option_type == "CE" else max(0, strike - spot)
    time_value = spot * 0.002  # ~0.2% of spot as time value (rough approximation)
    return round(intrinsic + time_value, 2)
```

### Files to Create
- `app/features/trading/strike.py` — `calculate_atm_strike(spot) -> int`
- `app/features/trading/service.py` — `handle_signal(signal, db) -> Trade`
- `app/features/trading/strike.py` — `simulate_premium(spot, strike, option_type) -> float`
- `app/features/trading/repository.py` — DB queries
- `app/features/trading/router.py` — `/trades` routes

### Trade Persistence
```python
async def handle_signal(signal: Signal, db: AsyncSession):
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
    db.add(trade)
    await db.commit()
    await db.refresh(trade)
    
    # Enqueue notification (TICKET-008)
    send_trade_notification.delay(str(trade.id))
    
    return trade
```

## Acceptance Criteria
- [ ] `calculate_atm_strike(22432)` → 22450
- [ ] `calculate_atm_strike(22424)` → 22400
- [ ] `calculate_atm_strike(22425)` → 22450 (round-half-up, documented)
- [ ] LONG signal → CE trade persisted
- [ ] SHORT signal → PE trade persisted
- [ ] Trade record has all required columns populated
- [ ] Trade persisted in a DB transaction (rollback on failure)
- [ ] `send_trade_notification.delay()` called after successful commit

## Dependencies
- TICKET-002 (PostgreSQL Trade model)
- TICKET-005 (Signal dataclass)
- TICKET-008 (Celery task — import, but that ticket implements it)

## Notes
- The premium mock should produce realistic values (tens to hundreds of rupees for NIFTY options) — avoid obviously wrong values like 0 or 1
- If DB commit fails, notification must NOT be enqueued (no orphan notifications)
