from __future__ import annotations

import argparse
from pathlib import Path

from src.db import DB_PATH, list_available_detailed, fetch_universe, load_data


def main():
    parser = argparse.ArgumentParser(description="Fetch market data for any universe")
    parser.add_argument("--universe", "-u", default="nifty50",
                        help="Universe slug (nifty50, nifty500, niftymidcap150) or path to JSON")
    parser.add_argument("--db", default=str(DB_PATH), help=f"SQLite DB path (default: {DB_PATH})")
    parser.add_argument("--years", type=int, default=10, help="Years of history (default: 10)")
    parser.add_argument("--force", action="store_true", help="Force re-fetch")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between requests (default: 0.5)")
    parser.add_argument("--query", "-q", nargs="?", const="1900-01-01", help="Query cached data since YYYY-MM-DD")
    parser.add_argument("--list", "-l", action="store_true", help="List available universes")
    parser.add_argument("--validate-only", action="store_true", help="Only validate symbols")
    parser.add_argument("--continue-on-error", action="store_true", help="Skip bad symbols")
    args = parser.parse_args()

    if args.list:
        for u in list_available_detailed():
            flag = " ERROR" if u.get("error") else ""
            print(f"  {u['slug']:20s}  {u['name']:30s}  {u['n_constituents']:4d} stocks{flag}")
        return

    if args.query:
        since = None if args.query == "1900-01-01" else args.query
        df = load_data(args.universe, args.db, since=since)
        if df.empty:
            print("No cached data found.")
        else:
            print(f"{len(df)} rows")
            print(df.to_string(index=False))
        return

    fetch_universe(args.universe, years=args.years, db_path=args.db,
                   force=args.force, delay=args.delay,
                   continue_on_error=args.continue_on_error,
                   validate_only=args.validate_only)


if __name__ == "__main__":
    main()
