# TICKET-004: DhanHQ WebSocket Consumer

**Branch:** `feature/TICKET-004-websocket-consumer`  
**Priority:** P1 — Depends on TICKET-003 (Redis window)  
**Estimate:** ~2h

## Summary
Build a resilient WebSocket consumer that connects to the DhanHQ market feed, subscribes to NIFTY 50 LTP updates, and pushes each tick through the shared ingestion pipeline. The consumer must survive disconnects, malformed frames, and silent periods without dying or silently stopping.

## Scope

### DhanHQ Connection
- Library: `dhanhq` Python library
- Instrument: NIFTY 50, Security ID: `13`
- Feed type: LTP (Last Traded Price)
- Use `DhanFeed` / `on_ticks` callback pattern

### Resilience Requirements
| Failure Mode | Handling |
|---|---|
| WebSocket disconnect | Exponential backoff reconnect (1s → 2s → 4s → max 60s) |
| Malformed frame | Log and skip; do not crash |
| Silent feed (market closed) | Heartbeat watchdog — if no tick in 30s, log warning; reconnect after 5min silence |
| Network timeout | Socket timeout + reconnect |
| Exception in tick handler | Catch, log, continue — never propagate to consumer loop |

### Files to Create
- `app/external/dhanhq/consumer.py` — `DhanFeedConsumer` class
  - `async start()` — connect + subscribe loop with reconnect
  - `async stop()` — graceful shutdown
  - `_on_tick(tick_data)` — parses tick, calls `ingest_tick()`
  - `_reconnect_loop()` — backoff reconnect logic
  - `_watchdog()` — asyncio task monitoring last tick timestamp
- `app/features/ingestion/pipeline.py` — `ingest_tick(security_id, ltp, ts)` — THE shared pipeline function
  - Appends to Redis window (TICKET-003)
  - Calls spike detector (TICKET-005)
  - This same function is called by replay endpoint (TICKET-006)

### Tick Schema (parsed from DhanHQ)
```python
@dataclass
class Tick:
    security_id: str
    ltp: float
    ts: datetime
```

### Startup Integration
- Consumer starts as a background asyncio task in FastAPI lifespan
- Graceful shutdown: cancel background task on app shutdown

## Acceptance Criteria
- [ ] Consumer connects and receives NIFTY 50 ticks during market hours
- [ ] Process survives a simulated disconnect (TCP reset) and reconnects
- [ ] Malformed JSON/binary frame is logged and skipped without crash
- [ ] `ingest_tick()` is the single entry point — replay endpoint uses same function
- [ ] Watchdog logs warning if no tick received in 30s
- [ ] Consumer state (connected/reconnecting/silent) exposed via GET /health

## Dependencies
- TICKET-001 (app structure)
- TICKET-003 (Redis window `append()`)

## Notes
- `dhanhq` WebSocket API may change; isolate behind an interface so mock is easy
- During market close, the replay endpoint (TICKET-006) is the primary test path
- Log tick count every 100 ticks for operational visibility
