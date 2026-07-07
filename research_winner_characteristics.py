import argparse
import numpy as np
import pandas as pd
from src.db import load_data, load_universe
from src.features import precompute_all_characteristics


def compute_cohens_d(series_a, series_b):
    n1, n2 = len(series_a), len(series_b)
    s1, s2 = series_a.std(ddof=1), series_b.std(ddof=1)
    pooled = np.sqrt(((n1 - 1) * s1**2 + (n2 - 1) * s2**2) / (n1 + n2 - 2))
    if pooled == 0:
        return 0.0
    return (series_a.mean() - series_b.mean()) / pooled


def main():
    parser = argparse.ArgumentParser(description="Identify characteristics of top-winning stocks")
    parser.add_argument("--horizon", type=int, default=5, help="Forward horizon in trading days")
    parser.add_argument("--universe", default="niftymidcap150", help="Universe slug")
    parser.add_argument("--years", type=int, default=3, help="Years of history")
    parser.add_argument("--top-pct", type=float, default=10, help="Top % labeled winners")
    parser.add_argument("--sample-interval", type=int, default=5, help="Sample every N days")
    args = parser.parse_args()

    print(f"{'='*78}")
    print(f"  WINNER CHARACTERISTICS RESEARCH")
    print(f"  Universe: {args.universe}  |  Horizon: {args.horizon}d  |  Top: {args.top_pct:.0f}%")
    print(f"{'='*78}")

    config = load_universe(args.universe)
    symbols = config["symbols"]
    print(f"\n  Loading {len(symbols)} stocks...")
    df_all = load_data(args.universe)
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=args.years)
    df_all = df_all[df_all["date"] >= cutoff]

    data = {}
    for sym in symbols:
        sub = df_all[df_all["symbol"] == sym].copy()
        if sub.empty:
            continue
        sub = sub.set_index("date")
        sub.index = pd.DatetimeIndex(sub.index)
        data[sym] = sub
    print(f"  Loaded {len(data)} stocks.")

    print(f"  Pre-computing characteristics...")
    char_data = precompute_all_characteristics(data, window=args.horizon)
    all_dates = sorted(set(d for s in char_data for d in char_data[s].index))
    sample_dates = all_dates[:-args.horizon:args.sample_interval]
    print(f"  Sample dates: {len(sample_dates)}")

    # Identify characteristic columns (exclude pure return metrics)
    sample_chars = next(iter(char_data.values()))
    char_names = [c for c in sample_chars.columns
                  if c not in ("return_over_window", "max_return", "ret_1d", "ret_5d")]

    obs = {name: [] for name in char_names}
    obs["is_winner"] = []
    obs["fwd_return"] = []

    for i, entry_date in enumerate(sample_dates):
        if (i + 1) % 30 == 0:
            print(f"  ... {i+1}/{len(sample_dates)} dates")
        end_idx = all_dates.index(entry_date) + args.horizon
        if end_idx >= len(all_dates):
            continue
        exit_date = all_dates[end_idx]
        records = []
        for sym in data:
            if exit_date not in data[sym].index or entry_date not in char_data[sym].index:
                continue
            ep = data[sym].loc[entry_date, "close"]
            xp = data[sym].loc[exit_date, "close"]
            ret = (xp / ep - 1) * 100
            chars = char_data[sym].loc[entry_date]
            records.append({"fwd_return": ret, "symbol": sym, "chars": chars})
        if not records:
            continue
        df_day = pd.DataFrame([r["chars"] for r in records])
        df_day["fwd_return"] = [r["fwd_return"] for r in records]
        threshold = df_day["fwd_return"].quantile(1 - args.top_pct / 100)
        df_day["is_winner"] = (df_day["fwd_return"] >= threshold).astype(int)
        for name in char_names:
            obs[name].extend(df_day[name].fillna(df_day[name].median()).tolist())
        obs["is_winner"].extend(df_day["is_winner"].tolist())
        obs["fwd_return"].extend(df_day["fwd_return"].tolist())

    df = pd.DataFrame(obs)
    winners = df[df["is_winner"] == 1]
    non_winners = df[df["is_winner"] == 0]
    print(f"\n  Total observations: {len(df)}  |  Winners: {len(winners)}  |  Non-winners: {len(non_winners)}")

    # Table 1: Effect sizes
    results = []
    for name in char_names:
        w_vals = winners[name]
        nw_vals = non_winners[name]
        if len(w_vals) < 2 or len(nw_vals) < 2:
            continue
        d = compute_cohens_d(w_vals, nw_vals)
        w_mean = w_vals.mean()
        nw_mean = nw_vals.mean()
        results.append({"char": name, "d": d, "w_mean": w_mean, "nw_mean": nw_mean, "diff": w_mean - nw_mean})
    results.sort(key=lambda r: abs(r["d"]), reverse=True)

    print(f"\n{'='*78}")
    print(f"  TABLE 1: CHARACTERISTICS RANKED BY EFFECT SIZE (Cohen's d)")
    print(f"{'='*78}")
    print(f"  {'Characteristic':<22} {'Winners':>9} {'Non-Win':>9} {'Diff':>9} {'|d|':>7} {'Strength':>10}")
    print(f"  {'-'*21:<22} {'-'*8:>9} {'-'*8:>9} {'-'*8:>9} {'-'*6:>7} {'-'*9:>10}")
    for r in results:
        ad = abs(r["d"])
        strength = "strong" if ad >= 0.8 else "medium" if ad >= 0.5 else "small" if ad >= 0.2 else "weak"
        print(f"  {r['char']:<22} {r['w_mean']:>+8.4f} {r['nw_mean']:>+8.4f} {r['diff']:>+8.4f} {ad:>6.3f} {strength:>10}")

    # Table 2: Quintile win rates (top 10 characteristics)
    top10 = [r["char"] for r in results[:10]]
    print(f"\n{'='*78}")
    print(f"  TABLE 2: WIN RATE BY QUINTILE (top 10 characteristics)")
    print(f"{'='*78}")
    print("  " + f"{'Characteristic':<22}" + "".join(f" {'Q'+str(i):>7}" for i in range(1, 6)) + "  Monotonic")
    for name in top10:
        col = df[name]
        df["_q"] = pd.qcut(col.rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
        quintile_wr = df.groupby("_q", observed=True)["is_winner"].mean() * 100
        wr_vals = [quintile_wr.get(i, 0) for i in range(1, 6)]
        increasing = all(wr_vals[i] <= wr_vals[i + 1] for i in range(4))
        decreasing = all(wr_vals[i] >= wr_vals[i + 1] for i in range(4))
        monotonic = "+" if increasing else "-" if decreasing else "~"
        print("  " + f"{name:<22}" + "".join(f" {v:>6.1f}%" for v in wr_vals) + f"  {monotonic:>9}")
    df.drop(columns=["_q"], errors="ignore", inplace=True)

    # Table 3: AND-gate alignment
    print(f"\n{'='*78}")
    print(f"  TABLE 3: AND-GATE ALIGNMENT CHECK")
    print(f"{'='*78}")
    gate_features = {
        "max_drawdown": "negative (dd <= -0.05)",
        "price_vs_low": "negative (pvl < 1.05)",
        "volume_vs_ma10": "positive (vma > 1.0)",
        "price_vs_high": "negative (pvh < 0.98)",
        "avg_true_range_pct": "positive (atr > median)",
        "volatility": "positive (vol > median)",
    }
    char_d_map = {r["char"]: r for r in results}
    print("  " + f"{'Gate':<22} {'Gate dir':<14} {'Char d':>7} {'Winner dir':<11} {'Aligned?':<10}")
    print("  " + f"{'-'*21:<22} {'-'*13:<14} {'-'*6:>7} {'-'*10:<11} {'-'*9:<10}")
    for feat, gate_dir in gate_features.items():
        if feat in char_d_map:
            r = char_d_map[feat]
            d = r["d"]
            winner_dir = "positive" if d > 0 else "negative"
            gate_direction = "positive" if "positive" in gate_dir else "negative"
            aligned = "YES" if winner_dir == gate_direction else "MISALIGN"
            print("  " + f"{feat:<22} {gate_dir:<14} {d:>+6.3f} {winner_dir:<11} {aligned:<10}")
        else:
            print(f"  {feat:<22} {gate_dir:<14} {'N/A':>7} {'N/A':<11} {'N/A':<10}")

    print(f"\n  Summary: |d| >= 0.5 (medium): {sum(1 for r in results if abs(r['d']) >= 0.5)}")
    print(f"           |d| >= 0.2 (small):  {sum(1 for r in results if abs(r['d']) >= 0.2)}")
    print(f"           |d| < 0.2 (weak):   {sum(1 for r in results if abs(r['d']) < 0.2)}")
    print()


if __name__ == "__main__":
    main()
