# Plan: TICKET-013 — Test Suite

## Branch
```bash
git checkout -b feature/TICKET-013-test-suite
```

## Implementation Steps

### Step 1 — `tests/conftest.py`
In-memory FakeRedis + FakePipeline fixtures, shared event_loop.

### Step 2 — `tests/test_strike.py`
Pure-function tests: `calculate_atm_strike`, `simulate_premium`.

### Step 3 — `tests/test_detector.py`
Async tests for `SpikeDetector.detect()` using `FakeRedis` + `PriceWindow`.

### Step 4 — `tests/test_window.py`
Async tests for `PriceWindow`: append, eviction, cold-start.

### Step 5 — `tests/test_pipeline.py`
Async tests for `ingest_tick()`: latency recording, signal dispatched.

### Step 6 — `tests/test_api.py`
HTTPX AsyncClient tests for REST endpoints using ASGITransport.

## Commit Message
```
feat(TICKET-013): add pytest test suite covering core logic and API endpoints
```
