"""Generate a NDJSON replay file that triggers at least one spike signal.

Each line uses the canonical replay tick format:
    {"security_id": "13", "ltp": 22450.5, "ts": "2026-07-10T09:31:04.221Z"}

Usage:
    # Write fixture used by tests and the README benchmark
    python scripts/generate_replay.py

    # Custom spike
    python scripts/generate_replay.py --ticks 200 --spike-pct 5.5
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate NDJSON replay tick file")
    parser.add_argument("--security-id", default="13")
    parser.add_argument("--ticks", type=int, default=120)
    parser.add_argument("--base-price", type=float, default=22000.0)
    parser.add_argument(
        "--spike-pct",
        type=float,
        default=5.5,
        help="Spike magnitude %% above base price (default: 5.5)",
    )
    parser.add_argument(
        "--spike-at",
        type=int,
        default=65,
        help="Tick index at which the spike fires (must be > 60)",
    )
    parser.add_argument(
        "--output",
        default="tests/fixtures/sample_replay.ndjson",
        help="Output file path (default: tests/fixtures/sample_replay.ndjson)",
    )
    args = parser.parse_args()

    if args.spike_at <= 60:
        print(
            "WARNING: --spike-at should be > 60 to fill the 60s window first",
            file=sys.stderr,
        )

    base = datetime(2026, 7, 10, 9, 30, 0, tzinfo=timezone.utc)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w") as f:
        for i in range(args.ticks):
            ts = base + timedelta(seconds=i)

            if i == args.spike_at:
                # Spike: raises price by spike_pct% above base
                price = round(args.base_price * (1 + args.spike_pct / 100), 2)
            else:
                # Slow drift — stays well below the 5% detection threshold
                price = round(args.base_price + (i % 5) * 0.5, 2)

            tick = {
                "security_id": args.security_id,
                "ltp": price,
                "ts": ts.isoformat().replace("+00:00", "Z"),
            }
            f.write(json.dumps(tick) + "\n")

    print(f"Written {args.ticks} ticks → {output_path}")
    print(f"Spike at tick {args.spike_at}: {args.base_price * (1 + args.spike_pct / 100):.2f}")


if __name__ == "__main__":
    main()
