from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

import numpy as np
from src.backtest import generate_signals, generate_momentum_signals, compute_momentum_stops, find_trading_dates, build_horizon_results
from src.db import load_symbol_data, load_universe, get_sector_map
from src.features import precompute_all_characteristics
from src.factors import generate_factor_signals, diversify_factor_signals
from src.reporting import forward_check_html, _classify_regime


def check_forward(universe_slug_or_path: str, date_str: str, horizons=(5, 10, 20), capital=10_000_000, output=None, strategy="contrarian", top=0):
    config = load_universe(universe_slug_or_path)
    universe_name = config.get("name", universe_slug_or_path)
    symbols = config["symbols"]
    entry_date = pd.Timestamp(date_str)

    print(f"\n{'='*70}")
    print(f"  FORWARD RETURN CHECK")
    print(f"  Universe:   {universe_name} ({len(symbols)} stocks)")
    print(f"  Entry date: {entry_date.date()} ({entry_date.strftime('%A')})")
    print(f"  Strategy:   {strategy.upper()}")
    print(f"  Capital:    INR {capital:,.0f}")
    print(f"{'='*70}")

    print(f"\n  Loading data from SQLite...")
    data = load_symbol_data(universe_slug_or_path)
    print(f"  Loaded {len(data)} stocks")

    if strategy == "momentum":
        all_vol = pd.concat({s: df["volume"] for s, df in data.items() if "volume" in df.columns}, axis=1)
        avg_vol = all_vol.mean() if not all_vol.empty else None
        sig = generate_momentum_signals(data, entry_date, avg_vol_series=avg_vol)
        print(f"  (no characteristics needed for momentum)")
    elif strategy == "factor":
        print(f"  Computing momentum and volatility...")

        available = sorted(set(d for s in data for d in data[s].index))
        if entry_date not in available:
            closest = [d for d in available if d >= entry_date]
            if not closest:
                print(f"  No trading data found on or after {entry_date.date()}")
                sys.exit(1)
            entry_date = closest[0]
            print(f"  Adjusted to nearest trading day: {entry_date.date()}")

        sector_map = get_sector_map(universe_slug_or_path)
        sig = generate_factor_signals(data, entry_date, sector_map)
    else:
        print(f"  Pre-computing characteristics...")
        char_data = precompute_all_characteristics(data, window=20)
        print(f"  Done.")

        if entry_date not in next(iter(char_data.values()), pd.DataFrame()).index:
            available = sorted(set(d for s in char_data for d in char_data[s].index))
            closest = [d for d in available if d >= entry_date]
            if not closest:
                print(f"  No trading data found on or after {entry_date.date()}")
                sys.exit(1)
            entry_date = closest[0]
            print(f"  Adjusted to nearest trading day: {entry_date.date()}")

        sig = generate_signals(data, char_data, entry_date)

    if sig.empty:
        print(f"\n  No signals generated on {entry_date.date()}.")
        sys.exit(1)

    # Sector diversification for factor strategy
    if strategy == "factor":
        sig = diversify_factor_signals(sig, sector_map, top)

    sig = sig.head(top) if strategy != "factor" else sig
    print(f"  Limited to top {len(sig)} signals")

    # Compute regime at entry date
    if strategy == "momentum":
        regime = {"trend_label": "Unknown", "trend_20d": 0, "action": "Unknown", "max_positions": 10}
    else:
        all_dates_fwd = sorted(set(d for s in data for d in data[s].index))
        all_prices = [data[s].loc[entry_date, "close"] for s in data if entry_date in data[s].index]
        idx_fwd = all_dates_fwd.index(entry_date) if entry_date in all_dates_fwd else -1
        if idx_fwd >= 20 and all_prices:
            past_date = all_dates_fwd[idx_fwd - 20]
            past_prices = [data[s].loc[past_date, "close"] for s in data if past_date in data[s].index]
            ret_20d = (np.mean(all_prices) / np.mean(past_prices) - 1) * 100 if past_prices else 0
        else:
            ret_20d = 0
        regime = _classify_regime(ret_20d)

    print(f"\n  Signals generated: {len(sig)}")
    print(f"  Regime: {regime.get('trend_label', 'N/A')} | {regime.get('action', 'N/A')}")

    if strategy == "momentum":
        print(f"  {'Rank':<5} {'Symbol':<18} {'Close':>8} {'Momentum':>10}")
        print(f"  {'-'*4:<5} {'-'*17:<18} {'-'*7:>8} {'-'*9:>10}")
        for _, row in sig.iterrows():
            mom_str = f"{row['momentum_12m']*100:+.1f}%" if 'momentum_12m' in row else "N/A"
            print(f"  {row['rank']:<5} {row['symbol']:<18} {row['close']:>8.2f} {mom_str:>10}")
    else:
        print(f"  {'Rank':<5} {'Symbol':<18} {'Close':>8} {'Conviction':>10}")
        print(f"  {'-'*4:<5} {'-'*17:<18} {'-'*7:>8} {'-'*9:>10}")
        for _, row in sig.iterrows():
            print(f"  {row['rank']:<5} {row['symbol']:<18} {row['close']:>8.2f} {row['conviction']:>10.4f}")

    horizon_data = build_horizon_results(data, sig, entry_date, horizons)

    if strategy == "factor":
        for h in horizons:
            hd = horizon_data.get(h, {})
            for r in hd.get("results", []):
                if r.get("min_intra_pct") is not None and r["min_intra_pct"] <= -3.0 and r.get("return_pct") is not None:
                    r["return_pct"] = max(r["return_pct"], -3.0)
                    r["exit_price"] = round(r["entry_price"] * 0.97, 2)
                    r["status"] = "stopped"
                    # find stop trigger date
                    for d in hd.get("dates", [])[1:]:
                        if r["symbol"] in data and d in data[r["symbol"]].index:
                            if data[r["symbol"]].loc[d, "close"] / r["entry_price"] - 1 <= -0.03:
                                r["exit_date"] = d
                                break
            if "df" in hd and not hd["df"].empty:
                hd["df"]["return_pct"] = [r.get("return_pct") for r in hd["results"]]
                hd["df"]["exit_price"] = [r.get("exit_price") for r in hd["results"]]
                hd["df"]["status"] = [r.get("status", "ok") for r in hd["results"]]

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
        winners = 0
        for r in hd["results"]:
            if r["return_pct"] is None:
                continue
            ret = r["return_pct"]
            min_s = f"{r['min_intra_pct']:+.2f}%" if r["min_intra_pct"] is not None else "N/A"
            status = "STOPPED" if r.get("status") == "stopped" else ("WIN" if ret > 0 else "LOSS")
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
    header = f"  {'Symbol':<18}" + "".join(f" {f'{h}d':>8}" for h in horizons) + f" {'Avg':>8}"
    print(header)
    for sym in all_rets:
        rets = all_rets[sym]
        vals = [v for v in rets.values() if v is not None]
        avg = sum(vals) / len(vals) if vals else 0
        line = f"  {sym:<18}" + "".join(f" {rets.get(h, 0):>+7.2f}%" if h in rets else f" {'N/A':>8}" for h in horizons)
        print(f"{line} {avg:>+7.2f}%")
    print(f"\n  Entry Date: {entry_date.date()}  |  Signals: {len(sig)}")
    if output:
        out_dir = os.path.dirname(output)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        html = forward_check_html(entry_date, sig, horizon_data, horizons, capital, regime=regime)
        with open(output, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\n  HTML report saved: {output}")


def main():
    parser = argparse.ArgumentParser(description="Check forward returns for any universe")
    parser.add_argument("--universe", "-u", default="nifty50",
                        help="Universe slug or path to JSON")
    parser.add_argument("--date", required=True, help="Historical date (YYYY-MM-DD)")
    parser.add_argument("--horizons", nargs="+", type=int, default=[5, 10, 20],
                        help="Forward horizons in trading days (default: 5 10 20)")
    parser.add_argument("--capital", type=float, default=10_000_000,
                        help="Starting capital (default: 10,000,000)")
    parser.add_argument("--strategy", "-s", default="contrarian", choices=["contrarian", "momentum", "factor"],
                        help="Strategy to check (default: contrarian)")
    parser.add_argument("--top", type=int, default=5,
                        help="Only trade top N ranked stocks (default: 3)")
    parser.add_argument("--output", default=None, help="Save HTML report to file")
    args = parser.parse_args()

    check_forward(args.universe, args.date, args.horizons, args.capital, args.output, args.strategy, args.top)


if __name__ == "__main__":
    main()
