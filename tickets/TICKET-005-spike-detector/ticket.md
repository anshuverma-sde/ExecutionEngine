# TICKET-005: Spike Detector

**Branch:** `feature/TICKET-005-spike-detector`  
**Priority:** P1 — Depends on TICKET-003 (Redis window)  
**Estimate:** ~1h

## Summary
Implement the spike detection logic that runs on every tick. Reads `P(t)` and `P(t-60)` from Redis, computes the 60-second return, and emits a Long or Short signal when the threshold is crossed.

## Spike Detection Algorithm

```
On every tick with price Pt at time t:
  1. Fetch P(t-60) from Redis rolling window
  2. If P(t-60) is None → insufficient history → skip (no signal)
  3. Compute return = (Pt - P(t-60)) / P(t-60)
  4. If return >= +0.05 → emit LONG signal
  5. If return <= -0.05 → emit SHORT signal
  6. Otherwise → no signal
```

## Scope

### Files to Create
- `app/features/spike_detection/detector.py` — `SpikeDetector` class
  - `async detect(security_id, ltp, ts) -> Signal | None`
  - Returns a `Signal` dataclass or `None`
- `app/features/spike_detection/schemas.py` — Signal dataclass
  ```python
  @dataclass
  class Signal:
      security_id: str
      direction: Literal["LONG", "SHORT"]
      current_price: float
      reference_price: float
      pct_change: float
      ts: datetime
      reason: str  # e.g. "+5.23% spike in 60s"
  ```

### Integration Point
In `app/features/ingestion/pipeline.py`:
```python
async def ingest_tick(security_id: str, ltp: float, ts: datetime):
    t0 = time.perf_counter()            # latency measurement start
    await price_window.append(security_id, ltp, ts)
    signal = await spike_detector.detect(security_id, ltp, ts)
    latency_ms = (time.perf_counter() - t0) * 1000  # latency measurement end
    record_latency(latency_ms)          # TICKET-011
    if signal:
        await handle_signal(signal)     # triggers TICKET-007
```

### Cooldown / Deduplication (Design Decision)
The spec does not specify a cooldown period. Decision: implement a **per-instrument 60-second cooldown** after a signal fires. Without this, a sustained 5%+ move would generate thousands of identical trades per minute.
- Store last signal timestamp per instrument in Redis: `last_signal:{security_id}`
- Skip if `now - last_signal_ts < 60s`
- Document this decision in README

## Acceptance Criteria
- [ ] Returns `None` when `P(t-60)` is unavailable (< 60s of history)
- [ ] Returns `LONG` signal when return >= 5%
- [ ] Returns `SHORT` signal when return <= -5%
- [ ] Returns `None` for moves between -5% and +5%
- [ ] 60-second cooldown prevents signal storm during sustained moves
- [ ] Latency measurement wraps the full detect call (see TICKET-011)
- [ ] Signal reason string formatted as "+5.23% spike in 60s"

## Dependencies
- TICKET-003 (Redis rolling window)

## Notes
- Edge case: if `P(t-60) == 0`, skip detection (division by zero guard)
- The 60s cooldown is an architectural decision that must be documented in README
- Keep detect() pure and fast — no I/O beyond the Redis reads already done in append()
