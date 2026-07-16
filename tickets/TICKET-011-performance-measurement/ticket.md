# TICKET-011: Performance Measurement (p99 < 50ms)

**Branch:** `feature/TICKET-011-performance-measurement`  
**Priority:** P1 — Hard requirement; measurement code must be in repo  
**Estimate:** ~1h

## Summary
Instrument the tick-to-signal path with latency measurement. Report p50, p95, p99, and max. The measurement code must live in the repo and the methodology must be described in README.

## Definition: "Tick-to-Signal"
Per spec: from the moment a tick enters the ingestion path to the moment the spike detector **emits a decision** (not including Postgres write, not including Celery).

```
t_start = time.perf_counter()  ← tick enters ingest_tick()
  ↓ Redis ZADD + ZREMRANGEBYSCORE (append to window)
  ↓ Redis ZRANGEBYSCORE (fetch P(t-60))
  ↓ Compute return, compare threshold
t_end = time.perf_counter()    ← signal decision returned
latency_ms = (t_end - t_start) * 1000
```

## Implementation

### Latency Collector
```python
# app/metrics/latency.py
import threading
from collections import deque
from typing import Optional
import numpy as np

class LatencyCollector:
    """Thread-safe rolling latency measurement."""
    
    def __init__(self, maxlen: int = 10_000):
        self._samples: deque[float] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
    
    def record(self, latency_ms: float):
        with self._lock:
            self._samples.append(latency_ms)
    
    def stats(self) -> dict:
        with self._lock:
            if not self._samples:
                return {"p50": 0, "p95": 0, "p99": 0, "max": 0, "count": 0}
            arr = list(self._samples)
        return {
            "p50_ms": round(float(np.percentile(arr, 50)), 3),
            "p95_ms": round(float(np.percentile(arr, 95)), 3),
            "p99_ms": round(float(np.percentile(arr, 99)), 3),
            "max_ms": round(float(max(arr)), 3),
            "count": len(arr),
        }
    
    def reset(self):
        with self._lock:
            self._samples.clear()

# Singleton
latency_collector = LatencyCollector()
```

### Integration in Pipeline
```python
# app/features/ingestion/pipeline.py
from app.metrics.latency import latency_collector
import time

async def ingest_tick(security_id: str, ltp: float, ts: datetime) -> Signal | None:
    t_start = time.perf_counter()
    
    await price_window.append(security_id, ltp, ts)
    signal = await spike_detector.detect(security_id, ltp, ts)
    
    latency_ms = (time.perf_counter() - t_start) * 1000
    latency_collector.record(latency_ms)
    
    return signal
```

### Metrics Endpoint
```python
# app/api/routes/metrics.py
@router.get("/metrics/latency")
async def get_latency_stats():
    return latency_collector.stats()
```

### Replay Response Integration
The `/debug/replay` response (TICKET-006) includes latency stats:
```json
{
  "processed": 1000,
  "signals": 3,
  "errors": 0,
  "latency_stats": {
    "p50_ms": 0.85,
    "p95_ms": 1.20,
    "p99_ms": 2.10,
    "max_ms": 4.90,
    "count": 1000
  }
}
```

## Files to Create
- `app/metrics/latency.py` — `LatencyCollector` class
- `app/api/routes/metrics.py` — `GET /metrics/latency`

## Expected Performance (Local Docker)
| Metric | Expected | Limit |
|---|---|---|
| p50 | < 1ms | — |
| p95 | < 5ms | — |
| p99 | < 20ms | — |
| max | < 50ms | Hard limit |

Most latency comes from 2 Redis round-trips (ZADD+ZREMRANGEBYSCORE pipeline, ZRANGEBYSCORE). On localhost this is typically < 1ms each.

## Acceptance Criteria
- [ ] `latency_collector.record()` called on every tick in `ingest_tick()`
- [ ] `GET /metrics/latency` returns p50/p95/p99/max/count
- [ ] `POST /debug/replay` response includes `latency_stats`
- [ ] README documents methodology (what is measured, where instrumentation is, how to reproduce)
- [ ] If p99 > 50ms, README explains where the time goes

## Dependencies
- TICKET-003 (Redis window — measured inside)
- TICKET-005 (Spike detector — measured inside)
- TICKET-006 (Replay endpoint — reports stats)

## Notes
- Use `time.perf_counter()` not `time.time()` — perf_counter has nanosecond resolution
- `numpy.percentile` is fine for offline analysis; for real-time p99 an HDR histogram (hdrpy) would be production-grade
- Reset collector between replay runs (add `?reset_metrics=true` to replay endpoint)
