"""Run the full research pipeline on any universe from SQLite cache.

Usage:
    python scan_universe.py --universe niftymidcap150
    python scan_universe.py --universe nifty50 --years 5
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "reverse_engineer"))

from data import fetch_index_data
from characteristics import precompute_all_characteristics, extract_characteristics
from compare import compare_characteristics, print_comparison_results
from validate import validate, print_validation_report
from fetch_universe_data import load_universe, get_db, DB_PATH


def load_data_from_sqlite(
    universe_slug_or_path: str,
    years: int = 3,
    db_path: str | Path = DB_PATH,
) -> dict[str, pd.DataFrame]:
    config = load_universe(universe_slug_or_path)
    symbols = config["symbols"]
    slug = config.get("slug", Path(universe_slug_or_path).stem)

    conn = get_db(Path(db_path))

    data: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        df = pd.read_sql_query(
            "SELECT date, open, high, low, close, volume, adj_close "
            "FROM daily_ohlcv WHERE symbol = ? ORDER BY date",
            conn, params=(sym,),
        )
        if not df.empty:
            dt = pd.to_datetime(df.pop("date"))
            df.index = pd.DatetimeIndex(dt.values)
            df.index.name = None
            data[sym] = df

    conn.close()
    return data


def scan(
    universe_slug_or_path: str,
    years: int = 3,
    horizon: int = 20,
    top_frac: float = 0.1,
    window: int = 20,
    db_path: str | Path = DB_PATH,
):
    print(f"{'='*70}")
    print(f"RESEARCH SCAN: {universe_slug_or_path}")
    print(f"{'='*70}")
    print(f"Horizon: {horizon}d | Top: {top_frac:.0%} | Window: {window}d | Data: {years}y")

    print(f"\nLoading data from SQLite...")
    data = load_data_from_sqlite(universe_slug_or_path, years=years, db_path=db_path)
    print(f"Loaded {len(data)} stocks")

    sample_sym = next(iter(data))
    print(f"  Range: {data[sample_sym].index.min().date()} to {data[sample_sym].index.max().date()}")

    print(f"\nPre-computing rolling characteristics (window={window})...")
    char_data = precompute_all_characteristics(data, window=window)
    print("Done.")

    print(f"\nComputing {horizon}-day forward returns...")
    all_rows = []
    for symbol, df in data.items():
        close = df["close"]
        fwd = close.shift(-horizon) / close - 1
        temp = pd.DataFrame({
            "symbol": symbol,
            "date": df.index.values,
            "fwd_return": fwd.values,
        })
        all_rows.append(temp)

    combined = pd.concat(all_rows).dropna(subset=["fwd_return"])
    print(f"Total observations: {len(combined)}")

    print(f"Labeling winners (top {top_frac:.0%} by forward return)...")
    tagged = []
    for date, group in combined.groupby("date"):
        n = len(group)
        n_winners = max(1, int(n * top_frac))
        sorted_group = group.sort_values("fwd_return", ascending=False)
        is_winner = pd.Series(False, index=sorted_group.index)
        is_winner.iloc[:n_winners] = True
        sorted_group["is_winner"] = is_winner.values
        tagged.append(sorted_group)

    all_tagged = pd.concat(tagged)
    n_winners = all_tagged["is_winner"].sum()
    print(f"Winner instances: {n_winners} ({100 * n_winners / len(all_tagged):.1f}%)")

    print(f"\nExtracting characteristics for all observations...")
    chars_df = extract_characteristics(char_data, all_tagged)
    for col in chars_df.select_dtypes(include=[np.number]).columns:
        chars_df[col] = chars_df[col].replace([np.inf, -np.inf], np.nan)
    print(f"Total characteristic instances: {len(chars_df)}")
    win_count = chars_df["is_winner"].sum()
    print(f"  Winners: {win_count}, Non-winners: {len(chars_df) - win_count}")

    print(f"\nComparing winners vs non-winners...")
    results = compare_characteristics(chars_df)
    print_comparison_results(results)

    print(f"\nRunning full validation...")
    try:
        index_df = fetch_index_data(years=years)
        index_series = index_df["close"] if not index_df.empty else None
    except Exception:
        index_series = None
    val_results = validate(chars_df, index_data=index_series)
    print_validation_report(val_results)

    print(f"\n{'='*70}")
    print(f"SCAN COMPLETE")
    print(f"{'='*70}")

    return chars_df, results, val_results


def main():
    parser = argparse.ArgumentParser(description="Run research scan on any universe")
    parser.add_argument("--universe", "-u", default="nifty50",
                        help="Universe slug or path to JSON")
    parser.add_argument("--years", type=int, default=3,
                        help="Years of data (default: 3)")
    parser.add_argument("--horizon", type=int, default=20,
                        help="Forward return horizon in days (default: 20)")
    parser.add_argument("--top-frac", type=float, default=0.1,
                        help="Top fraction labeled as winners (default: 0.1)")
    parser.add_argument("--window", type=int, default=20,
                        help="Characteristic rolling window (default: 20)")
    parser.add_argument("--db", default=str(DB_PATH),
                        help="SQLite DB path")
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
