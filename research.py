from __future__ import annotations

import argparse
from pathlib import Path

from src.db import DB_PATH
from src.research import scan


def main():
    parser = argparse.ArgumentParser(description="Run research scan on any universe")
    parser.add_argument("--universe", "-u", default="nifty50",
                        help="Universe slug or path to JSON")
    parser.add_argument("--years", type=int, default=3, help="Years of data (default: 3)")
    parser.add_argument("--horizon", type=int, default=20,
                        help="Forward return horizon in days (default: 20)")
    parser.add_argument("--top-frac", type=float, default=0.1,
                        help="Top fraction labeled as winners (default: 0.1)")
    parser.add_argument("--window", type=int, default=20,
                        help="Characteristic rolling window (default: 20)")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite DB path")
    args = parser.parse_args()

    scan(
        universe_slug_or_path=args.universe,
        years=args.years,
        horizon=args.horizon,
        top_frac=args.top_frac,
        window=args.window,
        db_path=args.db,
    )


if __name__ == "__main__":
    main()
