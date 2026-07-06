from __future__ import annotations

import argparse
from pathlib import Path

from src.backtest import BacktestConfig, print_report, run_backtest
from src.db import DB_PATH


def main():
    parser = argparse.ArgumentParser(description="Run backtest on any universe")
    parser.add_argument("--universe", "-u", default="nifty50",
                        help="Universe slug or path to JSON")
    parser.add_argument("--capital", type=float, default=10_000_000,
                        help="Starting capital (default: 10,000,000)")
    parser.add_argument("--horizons", nargs="+", type=int, default=[5, 10, 21],
                        help="Horizons in trading days (default: 5 10 21)")
    parser.add_argument("--years", type=int, default=3, help="Years of data (default: 3)")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite DB path")
    args = parser.parse_args()

    results = run_backtest(
        universe_slug_or_path=args.universe,
        years=args.years,
        capital=args.capital,
        horizons=args.horizons,
        db_path=args.db,
    )

    config = BacktestConfig(capital=args.capital, horizons=args.horizons, years=args.years)
    print_report(results, config)


if __name__ == "__main__":
    main()
