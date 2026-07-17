# Plan: TICKET-011 — Performance Measurement

## Branch
```bash
git checkout -b feature/TICKET-011-performance-measurement
```

## Implementation Steps

### Step 1 — `app/metrics/latency.py`
```python
import threading
from collections import deque
from typing import Any

import numpy as np


class LatencyCollector:
    """
    Thread-safe rolling latency measurement using a bounded deque.
    Stores last N samples and computes percentile statistics on demand.
    """

    def __init__(self, maxlen: int = 50_000):
        self._samples: deque[float] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def record(self, latency_ms: float) -> None:
        """Record a latency sample in milliseconds."""
        with self._lock:
            self._samples.append(latency_ms)

    def stats(self) -> dict[str, Any]:
        """Compute p50, p95, p99, max from current samples."""
        with self._lock:
            if not self._samples:
                return {
                    "p50_ms": 0.0,
                    "p95_ms": 0.0,
                    "p99_ms": 0.0,
                    "max_ms": 0.0,
                    "count": 0,
                    "note": "No samples recorded yet",
                }
            arr = list(self._samples)

        p50, p95, p99 = np.percentile(arr, [50, 95, 99])
        return {
            "p50_ms": round(float(p50), 3),
            "p95_ms": round(float(p95), 3),
            "p99_ms": round(float(p99), 3),
            "max_ms": round(float(max(arr)), 3),
            "count": len(arr),
        }

    def reset(self) -> None:
        """Clear all samples (for fresh replay runs)."""
        with self._lock:
            self._samples.clear()

    def meets_sla(self, p99_target_ms: float = 50.0) -> bool:
        """Returns True if current p99 is below target."""
        stats = self.stats()
        return stats["p99_ms"] <= p99_target_ms


# Module-level singleton — import and use directly
latency_collector = LatencyCollector()
```

### Step 2 — `app/api/routes/metrics.py`
```python
import logging
from fastapi import APIRouter

from app.metrics.latency import latency_collector

logger = logging.getLogger(__name__)
router = APIRouter(tags=["metrics"])


@router.get("/metrics/latency")
async def get_latency_stats():
    """
    Tick-to-signal latency percentiles.
    
    Measures from when a tick enters ingest_tick() to when the spike
    detector returns a decision. Does not include Postgres write or Celery.
    
    Target: p99 < 50ms
    """
    stats = latency_collector.stats()
    stats["sla_met"] = stats["p99_ms"] <= 50.0
    stats["sla_target_ms"] = 50.0
    return stats


@router.post("/metrics/reset")
async def reset_metrics():
    """Reset latency samples (useful before a clean replay run)."""
    latency_collector.reset()
    return {"status": "reset"}
```

### Step 3 — Integration in `app/features/ingestion/pipeline.py`
```python
import time
import logging
from datetime import datetime

from app.metrics.latency import latency_collector

logger = logging.getLogger(__name__)

async def ingest_tick(security_id: str, ltp: float, ts: datetime):
    """
    Shared ingestion entry point for live WebSocket and replay.
    
    Latency measurement scope:
      t_start → Redis ZADD+ZREMRANGEBYSCORE (window append)
              → Redis ZRANGEBYSCORE (fetch P(t-60))
              → spike threshold computation
      t_end   ← signal decision returned
    
    NOT measured: Postgres write, Celery enqueue, notification delivery.
    """
    t_start = time.perf_counter()
    try:
        await _price_window.append(security_id, ltp, ts)
        signal = await _spike_detector.detect(security_id, ltp, ts)
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        signal = None
    finally:
        latency_ms = (time.perf_counter() - t_start) * 1000
        latency_collector.record(latency_ms)

    if signal and _signal_handler:
        import asyncio
        asyncio.create_task(_dispatch_signal(signal))

    return signal
```

### Step 4 — `scripts/benchmark.py` (standalone measurement script)
```python
#!/usr/bin/env python3
"""
Benchmark the tick-to-signal pipeline using a generated replay file.
Usage: python scripts/benchmark.py [--ticks 1000] [--host http://localhost:8000]
"""
import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx

def generate_ticks(n: int) -> str:
    lines = []
    base = datetime(2026, 7, 10, 9, 30, 0, tzinfo=timezone.utc)
    # First 61 ticks at base price (fill window)
    for i in range(min(61, n)):
        ts = base + timedelta(seconds=i)
        lines.append(json.dumps({"security_id": "13", "ltp": 22000.0, "ts": ts.isoformat().replace("+00:00", "Z")}))
    # Remaining ticks with slight variation (no spikes, just throughput test)
    for i in range(61, n):
        ts = base + timedelta(seconds=i)
        price = 22000 + (i % 100) * 0.1  # oscillate, no 5% spike
        lines.append(json.dumps({"security_id": "13", "ltp": price, "ts": ts.isoformat().replace("+00:00", "Z")}))
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", type=int, default=1000)
    parser.add_argument("--host", default="http://localhost:8000")
    args = parser.parse_args()

    payload = generate_ticks(args.ticks)
    
    with httpx.Client(timeout=120) as client:
        # Reset state
        client.post(f"{args.host}/metrics/reset")
        client.post(f"{args.host}/debug/replay?reset_window=true&reset_metrics=true",
                    content=payload.encode(), headers={"Content-Type": "text/plain"})
        
        # Get results
        stats = client.get(f"{args.host}/metrics/latency").json()
    
    print(f"\nLatency Results ({args.ticks} ticks):")
    print(f"  p50:  {stats['p50_ms']:.3f} ms")
    print(f"  p95:  {stats['p95_ms']:.3f} ms")
    print(f"  p99:  {stats['p99_ms']:.3f} ms")
    print(f"  max:  {stats['max_ms']:.3f} ms")
    print(f"  SLA (p99 < 50ms): {'PASS ✓' if stats['sla_met'] else 'FAIL ✗'}")

if __name__ == "__main__":
    main()
```

## Expected Numbers & Analysis

| Environment | p50 | p95 | p99 | max |
|---|---|---|---|---|
| Local Docker (same host) | ~0.5ms | ~1.5ms | ~3ms | ~10ms |
| Remote Redis | ~2ms | ~5ms | ~15ms | ~30ms |

**Where time goes (if p99 > 50ms):**
1. Redis round-trip: 2 pipelined operations ~0.3ms local, ~2ms remote
2. ZRANGEBYSCORE on large window: O(log N) ~0.1ms for 60 entries
3. Python overhead (JSON encode/decode): ~0.1ms
4. asyncio event loop scheduling: ~0.05ms

If p99 exceeds 50ms, the most likely cause is Redis latency (remote host or high load). Solution: Redis on same host as app, or reduce JSON payload size in sorted set values.

## Verification
```bash
python scripts/benchmark.py --ticks 2000
# Run during replay to capture real numbers for README
```

## Commit Message
```
feat: add tick-to-signal latency measurement with p99 SLA tracking
```
