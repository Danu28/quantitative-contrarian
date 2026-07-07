import argparse
from src.backtest import run_backtest

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run backtest for any universe")
    parser.add_argument("--universe", "-u", default="nifty50", help="Universe slug or path to JSON (default: nifty50)")
    parser.add_argument("--years", type=int, default=3, help="Years of history (default: 3)")
    parser.add_argument("--capital", type=float, default=10_000_000, help="Starting capital (default: 10000000)")
    parser.add_argument("--horizons", type=int, nargs="+", default=[5, 10, 21], help="Horizons in trading days (default: 5 10 21)")

    args = parser.parse_args()
    run_backtest(
        universe_slug_or_path=args.universe,
        years=args.years,
        capital=args.capital,
        horizons=args.horizons,
    )
