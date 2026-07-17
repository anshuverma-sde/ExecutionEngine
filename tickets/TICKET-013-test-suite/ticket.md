# TICKET-013: Test Suite

**Branch:** `feature/TICKET-013-test-suite`  
**Priority:** P2 — Depends on all feature tickets  
**Estimate:** ~2h

## Summary
Write a pytest test suite covering the core business logic and API endpoints. Tests run without a live Redis or Postgres — all external I/O is replaced by in-memory fakes or `unittest.mock` stubs.

## Scope

### Test Modules
| File | What it tests |
|---|---|
| `tests/test_strike.py` | ATM strike calculation + premium simulation |
| `tests/test_detector.py` | Spike detector: cold start, LONG, SHORT, cooldown, edge cases |
| `tests/test_window.py` | Redis price window: append, eviction, get_price_at_t_minus_60 |
| `tests/test_pipeline.py` | Ingestion pipeline: latency recording, signal dispatch |
| `tests/test_api.py` | REST endpoints via HTTPX TestClient (no live server) |

### Fixtures (`tests/conftest.py`)
- `fake_redis` — in-memory Redis substitute (ZSETs, strings, pipeline, SET NX)
- `event_loop` — shared asyncio loop for the session

## Acceptance Criteria
- [ ] `pytest tests/` passes with zero failures
- [ ] Strike rounding covers banker's rounding edge case (22425 → 22450)
- [ ] Detector cold-start returns None
- [ ] Detector LONG/SHORT fire at exactly ±5%
- [ ] Cooldown suppresses duplicate signals
- [ ] Window evicts entries older than 60s
- [ ] Pipeline records latency on every tick
- [ ] API `/health` returns 200
- [ ] API `POST /ticks` accepts valid tick
- [ ] API `GET /trades` returns list

## Dependencies
- All feature tickets (001–012)

## Notes
- No real Redis or Postgres required — fake implementations in conftest.py
- Use `pytest-asyncio` for async test functions
- Use `httpx.AsyncClient` + `asgi_transport` for API tests
