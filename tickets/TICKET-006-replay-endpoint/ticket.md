# TICKET-006: Replay Endpoint

**Branch:** `feature/TICKET-006-replay-endpoint`  
**Priority:** P0 — Primary evaluation mechanism  
**Estimate:** ~1h

## Summary
Implement `POST /debug/replay` that accepts a newline-delimited JSON tick file and pushes every tick through the **exact same pipeline** as the live WebSocket consumer. This is how the evaluators will test the engine.

## Spec
```
POST /debug/replay
Content-Type: application/octet-stream  (or text/plain)

{"security_id": "13", "ltp": 22450.5, "ts": "2026-07-10T09:31:04.221Z"}
{"security_id": "13", "ltp": 22500.0, "ts": "2026-07-10T09:31:05.100Z"}
...
```

## Critical Requirement
> "This endpoint must push ticks through the exact same pipeline as the live WebSocket. Not a parallel code path."

This means: call `ingest_tick(security_id, ltp, ts)` from `app/features/ingestion/pipeline.py` — the same function the WebSocket consumer calls.

## Scope

### Files to Create/Modify
- `app/api/routes/debug.py` — replay router
- `app/api/router.py` — register debug router

### Implementation
```python
@router.post("/debug/replay")
async def replay(request: Request):
    body = await request.body()
    lines = body.decode().strip().split("\n")
    results = {"processed": 0, "errors": 0, "signals": 0}
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            tick = json.loads(line)
            ts = datetime.fromisoformat(tick["ts"].replace("Z", "+00:00"))
            signal = await ingest_tick(
                security_id=tick["security_id"],
                ltp=float(tick["ltp"]),
                ts=ts
            )
            results["processed"] += 1
            if signal:
                results["signals"] += 1
        except Exception as e:
            results["errors"] += 1
            logger.warning(f"Replay tick error: {e}, line: {line}")
    
    return results
```

### Return Schema
```json
{
  "processed": 1000,
  "errors": 2,
  "signals": 3,
  "latency_stats": {
    "p50_ms": 0.8,
    "p95_ms": 1.2,
    "p99_ms": 2.1,
    "max_ms": 5.4
  }
}
```

The `latency_stats` field piggybacks on TICKET-011's measurement infrastructure.

## Replay Timestamp Handling
- Ticks from replay file have historical timestamps
- The rolling window comparison must use the tick's `ts` field, NOT `datetime.now()`
- Redis window scores are the tick's timestamp (milliseconds) — replay is deterministic

## Acceptance Criteria
- [ ] `POST /debug/replay` accepts NDJSON body
- [ ] Each tick goes through `ingest_tick()` (same code path as WebSocket)
- [ ] Malformed lines are skipped (logged), processing continues
- [ ] Response includes processed/errors/signals counts + latency stats
- [ ] Replay with 60s-spanning ticks correctly triggers spike detection
- [ ] Redis window is cleared between replays (optional: `?reset_window=true` param)

## Dependencies
- TICKET-001 (FastAPI routing)
- TICKET-003 (Redis window — called via pipeline)
- TICKET-005 (Spike detector — called via pipeline)

## Notes
- Window reset between replays: add `?reset_window=true` query param that flushes `price_window:*` keys before processing — useful for clean test runs
- Streaming upload: for very large replay files, consider `StreamingResponse` reading — but batching lines is fine for assignment scope
