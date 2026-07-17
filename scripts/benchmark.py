"""
Benchmark runner: replay a NDJSON tick file and report p50/p95/p99 latency.

Usage:
    python scripts/benchmark.py --file tests/fixtures/sample_replay.ndjson \
        --url http://localhost:8000/debug/replay
"""
import argparse
import json
import time
from pathlib import Path


def compute_percentile(samples: list[float], pct: float) -> float:
    """Return the given percentile of a sorted list."""
    pass


def run_benchmark(replay_file: Path, api_url: str) -> dict:
    """
    POST each tick in the replay file to the ingestion endpoint and
    measure the round-trip latency.

    Returns a dict with p50, p95, p99, mean, and sample count.
    """
    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the ingestion pipeline")
    parser.add_argument("--file", default="tests/fixtures/sample_replay.ndjson")
    parser.add_argument("--url", default="http://localhost:8000/debug/replay")
    args = parser.parse_args()

    results = run_benchmark(Path(args.file), args.url)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
