"""
Generate a NDJSON replay file of synthetic NIFTY price ticks.

Usage:
    python scripts/generate_replay.py --output tests/fixtures/sample_replay.ndjson \
        --ticks 1000 --symbol NIFTY --base-price 22000

Each line is a JSON object with: symbol, ltp, timestamp, volume
"""
import argparse
import json
import random
import time
from pathlib import Path


def generate_ticks(
    symbol: str,
    base_price: float,
    n_ticks: int,
    spike_every: int = 50,
    spike_pct: float = 0.8,
) -> list[dict]:
    """Generate synthetic tick data with occasional spikes."""
    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate NDJSON replay file")
    parser.add_argument("--output", default="tests/fixtures/sample_replay.ndjson")
    parser.add_argument("--ticks", type=int, default=1000)
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--base-price", type=float, default=22000.0)
    args = parser.parse_args()

    ticks = generate_ticks(args.symbol, args.base_price, args.ticks)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w") as f:
        for tick in ticks:
            f.write(json.dumps(tick) + "\n")

    print(f"Written {len(ticks)} ticks to {output_path}")


if __name__ == "__main__":
    main()
