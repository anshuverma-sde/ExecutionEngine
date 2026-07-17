"""Benchmark runner: measure p50/p95/p99 tick-to-signal latency.

Strategy:
  1. POST the entire NDJSON replay file to POST /debug/replay?reset_metrics=true
  2. Read the latency stats from GET /metrics/latency (measured server-side,
     inside ingest_tick() — this is the authoritative measurement per spec)
  3. Also compute client-side round-trip latency for comparison

Usage:
    # Quick run against local server
    python scripts/benchmark.py

    # Custom file / URL
    python scripts/benchmark.py \\
        --file tests/fixtures/sample_replay.ndjson \\
        --url http://localhost:8000

    # Generate a larger fixture first
    python scripts/generate_replay.py --ticks 500 \\
        --out tests/fixtures/large_replay.ndjson
    python scripts/benchmark.py --file tests/fixtures/large_replay.ndjson

Exit code:
    0  — p99 <= 50ms (SLA met)
    1  — p99 > 50ms (SLA breached)
    2  — connection / HTTP error
"""
import argparse
import json
import sys
import time
from pathlib import Path


def compute_percentile(samples: list[float], pct: float) -> float:
    """Return the p-th percentile of a list of floats (0–100 scale)."""
    if not samples:
        return 0.0
    sorted_s = sorted(samples)
    idx = (pct / 100) * (len(sorted_s) - 1)
    lo = int(idx)
    hi = lo + 1
    if hi >= len(sorted_s):
        return sorted_s[-1]
    frac = idx - lo
    return sorted_s[lo] + frac * (sorted_s[hi] - sorted_s[lo])


def run_benchmark(replay_file: Path, base_url: str, reset_window: bool = True) -> dict:
    """POST the replay file and collect server-side + client-side latency stats.

    Returns a dict with:
      server_*  — latency measured inside ingest_tick() (authoritative)
      client_*  — wall-clock round-trip from here to server
      sla_met   — True if server p99 <= 50ms
      ticks     — number of ticks sent
      signals   — number of spike signals detected
    """
    import urllib.request
    import urllib.error

    rw = "true" if reset_window else "false"
    replay_url = f"{base_url}/debug/replay?reset_metrics=true&reset_window={rw}"
    metrics_url = f"{base_url}/metrics/latency"

    # ── Read the replay file ──────────────────────────────────────────────────
    if not replay_file.exists():
        print(f"ERROR: replay file not found: {replay_file}", file=sys.stderr)
        sys.exit(2)

    payload_bytes = replay_file.read_bytes()
    tick_count = sum(1 for line in payload_bytes.splitlines() if line.strip())

    print(f"Benchmark config:")
    print(f"  Replay file : {replay_file} ({tick_count} ticks)")
    print(f"  Server URL  : {base_url}")
    print()

    # ── POST replay ───────────────────────────────────────────────────────────
    print("Sending replay... ", end="", flush=True)
    t_start = time.perf_counter()
    try:
        req = urllib.request.Request(
            replay_url,
            data=payload_bytes,
            headers={"Content-Type": "application/x-ndjson"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            replay_body = json.loads(resp.read())
    except urllib.error.URLError as exc:
        print(f"\nERROR: could not reach server at {base_url}: {exc}", file=sys.stderr)
        sys.exit(2)

    client_total_ms = (time.perf_counter() - t_start) * 1000
    print(f"done in {client_total_ms:.1f}ms")

    processed = replay_body.get("processed", tick_count)
    signals = replay_body.get("signals", 0)
    errors = replay_body.get("errors", 0)
    replay_latency = replay_body.get("latency_stats", {})

    # ── Fetch authoritative server-side latency ───────────────────────────────
    try:
        with urllib.request.urlopen(metrics_url, timeout=10) as resp:
            server_stats = json.loads(resp.read())
    except urllib.error.URLError as exc:
        print(f"WARNING: could not fetch latency stats: {exc}", file=sys.stderr)
        server_stats = replay_latency  # fall back to replay response

    sla_target = 50.0
    p99 = server_stats.get("p99_ms", 0.0)
    sla_met = p99 <= sla_target

    results = {
        "ticks_sent": tick_count,
        "ticks_processed": processed,
        "signals_detected": signals,
        "errors": errors,
        "sla_target_ms": sla_target,
        "sla_met": sla_met,
        "server": {
            "p50_ms": server_stats.get("p50_ms", 0.0),
            "p95_ms": server_stats.get("p95_ms", 0.0),
            "p99_ms": server_stats.get("p99_ms", 0.0),
            "max_ms": server_stats.get("max_ms", 0.0),
            "sample_count": server_stats.get("count", 0),
        },
        "client": {
            "total_round_trip_ms": round(client_total_ms, 2),
            "avg_per_tick_ms": round(client_total_ms / max(tick_count, 1), 3),
        },
    }

    return results


def _print_report(results: dict) -> None:
    """Print a human-readable benchmark report."""
    sla = "✓ PASS" if results["sla_met"] else "✗ FAIL"
    s = results["server"]

    print()
    print("=" * 55)
    print("  INSTANT STRIKE — LATENCY BENCHMARK REPORT")
    print("=" * 55)
    print(f"  Ticks sent       : {results['ticks_sent']}")
    print(f"  Ticks processed  : {results['ticks_processed']}")
    print(f"  Signals detected : {results['signals_detected']}")
    print(f"  Errors           : {results['errors']}")
    print()
    print("  Server-side tick-to-signal latency")
    print(f"    p50  : {s['p50_ms']:>8.3f} ms")
    print(f"    p95  : {s['p95_ms']:>8.3f} ms")
    print(f"    p99  : {s['p99_ms']:>8.3f} ms   ← SLA target: <50ms")
    print(f"    max  : {s['max_ms']:>8.3f} ms")
    print(f"    n    : {s['sample_count']:>8}")
    print()
    print(f"  SLA (p99 < 50ms) : {sla}")
    print()
    c = results["client"]
    print(f"  Client round-trip: {c['total_round_trip_ms']:.1f}ms total "
          f"({c['avg_per_tick_ms']:.3f}ms/tick)")
    print("=" * 55)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark the Instant Strike ingestion pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--file",
        default="tests/fixtures/sample_replay.ndjson",
        help="Path to NDJSON replay file (default: tests/fixtures/sample_replay.ndjson)",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the running server (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON results instead of the formatted report",
    )
    parser.add_argument(
        "--reset-window",
        action="store_true",
        default=True,
        help="Clear the Redis price window before replay so the spike always fires (default: true)",
    )
    parser.add_argument(
        "--no-reset-window",
        dest="reset_window",
        action="store_false",
        help="Keep the existing Redis price window (spike may not fire if cooldown is active)",
    )
    args = parser.parse_args()

    results = run_benchmark(Path(args.file), args.url.rstrip("/"), reset_window=args.reset_window)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        _print_report(results)

    sys.exit(0 if results["sla_met"] else 1)


if __name__ == "__main__":
    main()
