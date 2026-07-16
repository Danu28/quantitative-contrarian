from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from src.db import DB_PATH


def factor_picks(
    date: pd.Timestamp,
    universe: str = "nifty50",
    top_n: int = 3,
    years: int = 2,
) -> pd.DataFrame:
    from src.factors import generate_factor_signals
    from src.db import load_data, load_symbol_data, get_sector_map

    df_all = load_data(universe, db_path=DB_PATH)
    cutoff = date - pd.DateOffset(days=365 * years)
    df_all = df_all[df_all["date"] >= cutoff]
    data = load_symbol_data(universe, db_path=DB_PATH, df_all=df_all)
    data = {s: df for s, df in data.items() if len(df) >= 200}
    if not data:
        return pd.DataFrame()

    available = sorted(set(d for s in data for d in data[s].index))
    entry = min((d for d in available if d >= date), default=None)
    if entry is None:
        return pd.DataFrame()

    sector_map = get_sector_map(universe)
    signals = generate_factor_signals(data, entry, sector_map)
    if signals.empty:
        return pd.DataFrame()
    result = signals.head(top_n).copy()
    result["entry_date"] = entry
    return result


def contrarian_picks(
    date: pd.Timestamp,
    universe: str = "nifty50",
    top_n: int = 3,
) -> tuple[pd.DataFrame, str]:
    from src.db import load_data, load_symbol_data
    from src.features import precompute_all_characteristics
    from src.backtest import generate_signals

    df_all = load_data(universe, db_path=DB_PATH)
    df_all = df_all[df_all["date"] <= date]
    data = load_symbol_data(universe, db_path=DB_PATH, df_all=df_all)
    data = {s: df for s, df in data.items() if len(df) >= 100}
    if not data:
        return pd.DataFrame(), ""

    char_data = precompute_all_characteristics(data, window=20)
    available = sorted(set(d for s in char_data for d in char_data[s].index))
    entry = min((d for d in available if d >= date), default=None)
    if entry is None:
        return pd.DataFrame(), ""

    # Regime at entry
    all_prices = [data[s].loc[entry, "close"] for s in data if entry in data[s].index]
    idx = available.index(entry)
    regime_label = ""
    if idx >= 20 and all_prices:
        past_date = available[idx - 20]
        past_prices = [data[s].loc[past_date, "close"] for s in data if past_date in data[s].index]
        if past_prices:
            ret_20d = (np.mean(all_prices) / np.mean(past_prices) - 1) * 100
            from src.reporting import _classify_regime
            regime_label = _classify_regime(ret_20d).get("trend_label", "")

    signals = generate_signals(data, char_data, entry)
    if signals.empty:
        return pd.DataFrame(), regime_label

    result = signals.head(top_n).copy()
    result["entry_date"] = entry
    return result, regime_label


def forward_returns(
    picks: pd.DataFrame,
    horizons: list[int],
) -> pd.DataFrame:
    if picks.empty:
        return pd.DataFrame()
    from src.db import load_data, load_symbol_data

    universe = "nifty50"
    df_all = load_data(universe, db_path=DB_PATH)
    data = load_symbol_data(universe, db_path=DB_PATH, df_all=df_all)
    all_dates = sorted(set(d for s in data for d in data[s].index))

    results = picks.copy()
    for h in horizons:
        col = f"ret_{h}d"
        results[col] = np.nan
        for i, row in picks.iterrows():
            sym = row["symbol"]
            entry = row["entry_date"]
            if sym not in data or entry not in data[sym].index:
                continue
            ep = data[sym].loc[entry, "close"]
            idx = all_dates.index(entry) if entry in all_dates else -1
            fwd_idx = idx + h
            if fwd_idx < len(all_dates):
                fwd_date = all_dates[fwd_idx]
                if fwd_date in data[sym].index:
                    xp = data[sym].loc[fwd_date, "close"]
                    results.at[i, col] = (xp / ep - 1) * 100
    return results


def print_comparison(
    factor: pd.DataFrame,
    contrarian: pd.DataFrame,
    entry_date: pd.Timestamp,
    regime: str,
):
    horizons = [5, 10, 15, 20]
    sep = "=" * 80

    print(f"\n{sep}")
    print(f"  SIDE-BY-SIDE COMPARISON — Entry: {entry_date.date()}")
    if regime:
        print(f"  Regime: {regime}")
    print(f"{sep}")

    strategies = [("FACTOR MODEL", factor), ("CONTRARIAN", contrarian)]
    for name, df in strategies:
        print(f"\n  [{name}]")
        if df.empty:
            print(f"  No signals")
            continue
        header = f"  {'Rank':<5} {'Symbol':<18} {'Entry':>8} {'Conviction':>10}"
        for h in horizons:
            header += f" {f'Ret{h}d':>8}"
        header += f" {'Avg':>8}"
        print(header)
        print(f"  {'-'*4:<5} {'-'*17:<18} {'-'*7:>8} {'-'*9:>10}" +
              "".join(f" {'-'*7:>8}" for _ in horizons) + f" {'-'*7:>8}")
        for _, row in df.iterrows():
            rets = [row.get(f"ret_{h}d", np.nan) for h in horizons]
            vals = [v for v in rets if not np.isnan(v)]
            avg = np.mean(vals) if vals else np.nan
            line = f"  {row.get('rank', 1):<5} {row['symbol']:<18} {row.get('close', 0):>8.2f} {row.get('conviction', 0):>10.4f}"
            for r in rets:
                line += f" {r:>+7.2f}%" if not np.isnan(r) else f" {'N/A':>8}"
            line += f" {avg:>+7.2f}%" if not np.isnan(avg) else f" {'N/A':>8}"
            print(line)

    # Winner comparison
    print(f"\n{sep}")
    print(f"  BEST PICK AT 10d")
    print(f"{sep}")
    for name, df in strategies:
        if df.empty:
            print(f"  {name:<15}: No signal")
        elif 10 in horizons and f"ret_10d" in df.columns:
            best = df.loc[df[f"ret_10d"].fillna(-999).idxmax()]
            ret = best.get(f"ret_10d", np.nan)
            ret_str = f"{ret:+.2f}%" if not np.isnan(ret) else "N/A"
            print(f"  {name:<15}: {best['symbol']:<18} 10d return: {ret_str}")
    print(f"{sep}")


def main():
    parser = argparse.ArgumentParser(
        description="Compare Factor Model vs Contrarian Strategy picks",
    )
    parser.add_argument("--date", required=True, help="Entry date (YYYY-MM-DD)")
    parser.add_argument("--universe", default="nifty50", help="Universe slug")
    parser.add_argument("--top-n", type=int, default=3, help="Top N picks per strategy")
    parser.add_argument("--output", "-o", default=None, help="Save HTML report to path")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite DB path")
    args = parser.parse_args()

    entry_date = pd.Timestamp(args.date)
    print(f"{'='*80}")
    print(f"  STRATEGY COMPARISON — Entry: {entry_date.date()}")
    print(f"  Universe: {args.universe}  |  Top N: {args.top_n}")
    print(f"{'='*80}")

    horizons = [5, 10, 15, 20]
    factor = factor_picks(entry_date, args.universe, args.top_n)
    contra, regime = contrarian_picks(entry_date, args.universe, args.top_n)

    if regime:
        print(f"  Regime: {regime}")
    print(f"  Factor Model signals:   {len(factor)}")
    print(f"  Contrarian signals:     {len(contra)}")

    fwd_factor = forward_returns(factor, horizons) if not factor.empty else pd.DataFrame()
    fwd_contra = forward_returns(contra, horizons) if not contra.empty else pd.DataFrame()

    print_comparison(fwd_factor, fwd_contra, entry_date, regime)


if __name__ == "__main__":
    main()
