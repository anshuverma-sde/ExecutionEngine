"""LatencyCollector singleton — records and reports pipeline latency."""
import logging
import time

logger = logging.getLogger(__name__)


class LatencyCollector:
    """Thread-safe collector for end-to-end pipeline latency measurements."""

    _instance: "LatencyCollector | None" = None

    def __new__(cls) -> "LatencyCollector":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._samples: list[float] = []
        return cls._instance

    def record(self, latency_ms: float) -> None:
        """Record a single latency measurement in milliseconds."""
        pass

    def percentile(self, pct: float) -> float | None:
        """
        Return the given percentile (0–100) of recorded latencies.

        Returns None if no samples have been recorded.
        """
        pass

    def stats(self) -> dict:
        """Return p50, p95, p99, mean and sample count as a dict."""
        pass

    def reset(self) -> None:
        """Clear all recorded samples (useful between benchmark runs)."""
        pass
