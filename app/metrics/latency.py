"""Tick-to-signal latency measurement.

Measurement scope (per spec):
  From when a tick enters ingest_tick() to when the spike detector returns
  a decision. Does NOT include Postgres write or Celery enqueue.

Uses a thread-safe bounded deque so Celery workers (sync threads) can also
record samples without corrupting the collector.
"""
import threading
from collections import deque
from typing import Any

import numpy as np

_MAX_SAMPLES = 50_000   # Rolling window — oldest samples auto-evicted


class LatencyCollector:
    """Thread-safe rolling latency collector.

    A module-level singleton (latency_collector) is the canonical instance.
    """

    def __init__(self, maxlen: int = _MAX_SAMPLES) -> None:
        self._samples: deque[float] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def record(self, latency_ms: float) -> None:
        """Record a single latency sample in milliseconds."""
        with self._lock:
            self._samples.append(latency_ms)

    def percentile(self, pct: float) -> float | None:
        """Return the given percentile (0–100). Returns None if no samples."""
        with self._lock:
            if not self._samples:
                return None
            arr = list(self._samples)
        return float(np.percentile(arr, pct))

    def stats(self) -> dict[str, Any]:
        """Return p50, p95, p99, max, count, and SLA status."""
        with self._lock:
            if not self._samples:
                return {
                    "p50_ms": 0.0,
                    "p95_ms": 0.0,
                    "p99_ms": 0.0,
                    "max_ms": 0.0,
                    "count": 0,
                    "sla_met": True,   # vacuously true — no data yet
                }
            arr = list(self._samples)

        p50, p95, p99 = np.percentile(arr, [50, 95, 99])
        max_ms = float(max(arr))
        return {
            "p50_ms": round(float(p50), 3),
            "p95_ms": round(float(p95), 3),
            "p99_ms": round(float(p99), 3),
            "max_ms": round(max_ms, 3),
            "count": len(arr),
            "sla_met": float(p99) <= 50.0,   # hard requirement: p99 < 50ms
        }

    def reset(self) -> None:
        """Clear all samples — useful before benchmark / replay runs."""
        with self._lock:
            self._samples.clear()


# Module-level singleton — import this everywhere
latency_collector = LatencyCollector()
