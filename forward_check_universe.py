"""Forward return check for any universe from SQLite cache.

Usage:
    python forward_check_universe.py --universe niftymidcap150 --date 2026-06-01
    python forward_check_universe.py --universe nifty50 --date 2026-07-01 --horizons 5 10 20
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "reverse_engineer"))

from characteristics import precompute_all_characteristics
from signal_generator import generate_signals, HORIZON
from fetch_universe_data import load_universe, get_db, DB_PATH


def load_data_from_sqlite(
    universe_slug_or_path: str,
    years: int = 3,
    db_path: str | Path = DB_PATH,
) -> dict[str, pd.DataFrame]:
    config = load_universe(universe_slug_or_path)
    symbols = config["symbols"]
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


def find_trading_dates(data, date, ahead):
    all_dates = sorted(set(d for s in data for d in data[s].index))
    available = [d for d in all_dates if d >= date]
    if not available:
        return []
    return available[:ahead + 1]


def build_horizon_results(data, sig, entry_date, horizons):
    horizon_data = {}
    for h in horizons:
        dates = find_trading_dates(data, entry_date, h)
        if len(dates) <= 1:
            horizon_data[h] = {"dates": dates, "results": [], "df": pd.DataFrame()}
            continue
        exit_date = dates[-1]
        results = []
        for _, row in sig.iterrows():
            symbol = row["symbol"]
            ep = row["close"]
            if symbol not in data or exit_date not in data[symbol].index:
                results.append({"symbol": symbol, "entry_date": entry_date, "exit_date": exit_date,
                                "entry_price": ep, "exit_price": None, "return_pct": None,
                                "min_intra_pct": None, "status": "no_data"})
                continue
            xp = data[symbol].loc[exit_date, "close"]
            ret = (xp / ep - 1) * 100
            min_ret = None
            for d in dates[1:]:
                if d in data[symbol].index:
                    r = (data[symbol].loc[d, "close"] / ep - 1) * 100
                    if min_ret is None or r < min_ret:
                        min_ret = r
            results.append({"symbol": symbol, "entry_date": entry_date, "exit_date": exit_date,
                            "entry_price": round(ep, 2), "exit_price": round(xp, 2),
                            "return_pct": round(ret, 2), "min_intra_pct": round(min_ret, 2) if min_ret is not None else None,
                            "status": "ok"})
        horizon_data[h] = {"dates": dates, "exit_date": exit_date, "results": results, "df": pd.DataFrame(results)}
    return horizon_data


def check_forward(universe_slug_or_path: str, date_str: str, horizons=(5, 10, 20), capital=10_000_000):
    config = load_universe(universe_slug_or_path)
    universe_name = config.get("name", universe_slug_or_path)
    symbols = config["symbols"]
    entry_date = pd.Timestamp(date_str)

    print(f"\n{'='*70}")
    print(f"  FORWARD RETURN CHECK")
    print(f"  Universe:   {universe_name} ({len(symbols)} stocks)")
    print(f"  Entry date: {entry_date.date()} ({entry_date.strftime('%A')})")
    print(f"  Capital:    INR {capital:,.0f}")
    print(f"{'='*70}")

    print(f"\n  Loading data from SQLite...")
    data = load_data_from_sqlite(universe_slug_or_path, years=3)
    print(f"  Loaded {len(data)} stocks")

    print(f"  Pre-computing characteristics...")
    char_data = precompute_all_characteristics(data, window=HORIZON)
    print(f"  Done.")

    if entry_date not in char_data.get(list(char_data.keys())[0], pd.DataFrame()).index:
        available = sorted(set(d for s in char_data for d in char_data[s].index))
        closest = [d for d in available if d >= entry_date]
        if not closest:
            print(f"  No trading data found on or after {entry_date.date()}")
            return
        entry_date = closest[0]
        print(f"  Adjusted to nearest trading day: {entry_date.date()}")

    sig = generate_signals(data, char_data, entry_date)

    if sig.empty:
        print(f"\n  No signals generated on {entry_date.date()}.")
        return

    print(f"\n  Signals generated: {len(sig)}")
    print(f"  {'Rank':<5} {'Symbol':<18} {'Close':>8} {'Conviction':>10}")
    print(f"  {'-'*4:<5} {'-'*17:<18} {'-'*7:>8} {'-'*9:>10}")
    for _, row in sig.iterrows():
        print(f"  {row['rank']:<5} {row['symbol']:<18} {row['close']:>8.2f} {row['conviction']:>10.4f}")

    horizon_data = build_horizon_results(data, sig, entry_date, horizons)

    for h in horizons:
        hd = horizon_data.get(h, {})
        df = hd.get("df", pd.DataFrame())
        dates = hd.get("dates", [])
        if len(dates) <= 1:
            print(f"\n  [HORIZON {h}d] Not enough data ahead")
            continue
        exit_date = hd["exit_date"]
        actual_days = (exit_date - entry_date).days
        n_trading = len(dates) - 1
        print(f"\n{'-'*70}")
        print(f"  {h} TRADING DAYS -- Entry {entry_date.date()} -> Exit {exit_date.date()} ({actual_days} cal days, {n_trading} trading days)")
        print(f"{'-'*70}")
        print(f"  {'Symbol':<18} {'Entry':>9} {'Exit':>9} {'Return':>8} {'Min Intra':>9} {'Status':<10}")
        print(f"  {'-'*17:<18} {'-'*8:>9} {'-'*8:>9} {'-'*7:>8} {'-'*8:>9} {'-'*9:<10}")
        winners = 0
        for r in hd["results"]:
            if r["return_pct"] is None:
                continue
            ret = r["return_pct"]
            min_s = f"{r['min_intra_pct']:+.2f}%" if r["min_intra_pct"] is not None else "N/A"
            status = "WIN" if ret > 0 else "LOSS"
            if ret > 0:
                winners += 1
            print(f"  {r['symbol']:<18} {r['entry_price']:>9.2f} {r['exit_price']:>9.2f} {ret:>+8.2f}% {min_s:>9} {status:<10}")
        avg_ret = df["return_pct"].mean()
        print(f"\n  Summary: {winners}/{len(hd['results'])} wins ({winners/len(hd['results'])*100:.0f}%) | Avg: {avg_ret:+.2f}%")

    all_rets = {}
    for _, row in sig.iterrows():
        sym = row["symbol"]
        all_rets[sym] = {}
        for h in horizons:
            for r in horizon_data.get(h, {}).get("results", []):
                if r["symbol"] == sym and r["return_pct"] is not None:
                    all_rets[sym][h] = r["return_pct"]

    print(f"\n{'='*70}")
    print(f"  CROSS-HORIZON SUMMARY")
    print(f"{'='*70}")
    header = f"  {'Symbol':<18}"
    for h in horizons:
        header += f" {f'{h}d':>8}"
    header += f" {'Avg':>8}"
    print(header)
    print(f"  {'-'*17:<18}" + " ".join(f"{'-'*7:>8}" for _ in horizons) + f" {'-'*6:>8}")
    for sym in all_rets:
        rets = all_rets[sym]
        vals = [v for v in rets.values() if v is not None]
        avg = sum(vals) / len(vals) if vals else 0
        line = f"  {sym:<18}"
        for h in horizons:
            line += f" {rets.get(h, 0):>+7.2f}%" if h in rets else f" {'N/A':>8}"
        line += f" {avg:>+7.2f}%"
        print(line)
    print(f"\n  Entry Date: {entry_date.date()}  |  Signals: {len(sig)}")


def main():
    parser = argparse.ArgumentParser(description="Check forward returns for any universe")
    parser.add_argument("--universe", "-u", default="niftymidcap150",
                        help="Universe slug or path to JSON")
    parser.add_argument("--date", required=True,
                        help="Historical date (YYYY-MM-DD)")
    parser.add_argument("--horizons", nargs="+", type=int, default=[5, 10, 20],
                        help="Forward horizons in trading days (default: 5 10 20)")
    parser.add_argument("--capital", type=float, default=10_000_000,
                        help="Starting capital for context (default: 10,000,000)")
    args = parser.parse_args()

    check_forward(args.universe, args.date, args.horizons, args.capital)


if __name__ == "__main__":
    main()
