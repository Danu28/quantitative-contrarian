from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import mannwhitneyu

from src.db import DB_PATH, load_data, load_universe
from src.features import (
    extract_characteristics,
    get_characteristic_names,
    precompute_all_characteristics,
)

NIFTY_INDEX_TICKER = "^NSEI"


def load_data_from_sqlite(
    universe_slug_or_path: str,
    years: int = 3,
    db_path: str | Path = DB_PATH,
) -> dict[str, pd.DataFrame]:
    config = load_universe(universe_slug_or_path)
    symbols = config["symbols"]
    df_all = load_data(universe_slug_or_path, db_path=db_path)
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=365 * years)
    df_all = df_all[df_all["date"] >= cutoff]
    data: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        sub = df_all[df_all["symbol"] == sym].copy()
        if sub.empty:
            continue
        sub = sub.set_index("date")
        sub.index = pd.DatetimeIndex(sub.index)
        data[sym] = sub
    return data


def fetch_index_data(years: int = 10) -> pd.DataFrame:
    df = yf.download(NIFTY_INDEX_TICKER, period=f"{years}y", progress=False, auto_adjust=True)
    if df.empty:
        return pd.DataFrame()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]
    return df


def compare_characteristics(
    chars_df: pd.DataFrame,
    alpha: float = 0.05,
    correction: str = "bonferroni",
) -> pd.DataFrame:
    winners = chars_df[chars_df["is_winner"]]
    non_winners = chars_df[~chars_df["is_winner"]]
    feature_names = get_characteristic_names()
    results = []
    for feat in feature_names:
        if feat not in chars_df.columns:
            continue
        w = winners[feat].dropna()
        nw = non_winners[feat].dropna()
        if len(w) < 5 or len(nw) < 5:
            continue
        try:
            stat, p_value = mannwhitneyu(w, nw, alternative="two-sided")
        except ValueError:
            continue
        mean_w = w.mean()
        mean_nw = nw.mean()
        std_w = w.std()
        std_nw = nw.std()
        pooled_std = np.sqrt((std_w**2 + std_nw**2) / 2)
        cohens_d = (mean_w - mean_nw) / pooled_std if pooled_std > 0 else 0
        diff_pct = ((mean_w - mean_nw) / abs(mean_nw) * 100) if mean_nw != 0 else np.nan
        results.append({
            "characteristic": feat,
            "winner_mean": mean_w,
            "non_winner_mean": mean_nw,
            "winner_std": std_w,
            "non_winner_std": std_nw,
            "difference_pct": diff_pct,
            "cohens_d": cohens_d,
            "mann_whitney_u_stat": stat,
            "p_value": p_value,
            "n_winners": len(w),
            "n_non_winners": len(nw),
        })

    result_df = pd.DataFrame(results)

    if correction == "bonferroni" and len(result_df) > 0:
        n_tests = len(result_df)
        result_df["p_corrected"] = np.clip(result_df["p_value"] * n_tests, 0, 1)
        result_df["significant"] = result_df["p_corrected"] < alpha
    else:
        result_df["p_corrected"] = result_df["p_value"]
        result_df["significant"] = result_df["p_value"] < alpha

    result_df = result_df.sort_values("cohens_d", key=abs, ascending=False)
    result_df["rank"] = range(1, len(result_df) + 1)
    return result_df


def print_comparison_results(results: pd.DataFrame):
    print(f"\n{'='*90}")
    print(f"CHARACTERISTIC COMPARISON: Winners vs Non-Winners")
    print(f"{'='*90}")
    print(f"{'Rank':<5} {'Characteristic':<25} {'Winner Mean':<12} {'Non-Winner':<12} {'Cohen d':<10} {'p_corr':<10} {'Sig':<6}")
    print(f"{'-'*90}")
    for _, row in results.iterrows():
        sig = "***" if row["significant"] else ""
        print(f"{row['rank']:<5} {row['characteristic']:<25} {row['winner_mean']:<12.4f} {row['non_winner_mean']:<12.4f} {row['cohens_d']:<10.4f} {row['p_corrected']:<10.4f} {sig:<6}")
    print(f"{'='*90}")
    n_sig = results["significant"].sum()
    print(f"Significant characteristics (p < 0.05, Bonferroni): {n_sig} / {len(results)}")
    print(f"{'='*90}\n")


def chronological_split(
    chars_df: pd.DataFrame,
    split_frac: float = 0.7,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = sorted(chars_df["winner_date"].unique())
    split_idx = int(len(dates) * split_frac)
    cutoff = dates[split_idx]
    in_sample = chars_df[chars_df["winner_date"] <= cutoff].copy()
    out_sample = chars_df[chars_df["winner_date"] > cutoff].copy()
    return in_sample, out_sample


def regime_split(
    chars_df: pd.DataFrame,
    index_data: pd.Series,
) -> dict[str, pd.DataFrame]:
    index_rets = index_data.pct_change()
    regimes = {}
    for date, group in chars_df.groupby("winner_date"):
        if date in index_rets.index:
            ret = index_rets.loc[date]
            if ret > 0.01:
                regimes.setdefault("bull", []).append(group)
            elif ret < -0.01:
                regimes.setdefault("bear", []).append(group)
            else:
                regimes.setdefault("sideways", []).append(group)
    return {k: pd.concat(v) for k, v in regimes.items()}


def permutation_test(
    chars_df: pd.DataFrame,
    feature: str,
    n_permutations: int = 1000,
) -> float:
    actual_w = chars_df[chars_df["is_winner"]][feature].dropna()
    actual_nw = chars_df[~chars_df["is_winner"]][feature].dropna()
    if len(actual_w) < 5 or len(actual_nw) < 5:
        return 1.0
    try:
        actual_stat, _ = mannwhitneyu(actual_w, actual_nw, alternative="two-sided")
    except ValueError:
        return 1.0
    combined = pd.concat([actual_w, actual_nw]).values.copy()
    n_w = len(actual_w)
    count_extreme = 0
    for _ in range(n_permutations):
        np.random.shuffle(combined)
        perm_w = combined[:n_w]
        perm_nw = combined[n_w:]
        try:
            perm_stat, _ = mannwhitneyu(perm_w, perm_nw, alternative="two-sided")
        except ValueError:
            continue
        if abs(perm_stat) >= abs(actual_stat):
            count_extreme += 1
    return count_extreme / n_permutations


def validate(
    chars_df: pd.DataFrame,
    index_data: pd.Series = None,
    split_frac: float = 0.7,
    alpha: float = 0.05,
    min_cohens_d: float = 0.1,
) -> dict:
    results = {}
    in_sample, out_sample = chronological_split(chars_df, split_frac)
    results["n_in_sample"] = len(in_sample)
    results["n_out_sample"] = len(out_sample)
    in_results = compare_characteristics(in_sample, alpha=alpha)
    out_results = compare_characteristics(out_sample, alpha=alpha)
    results["in_sample"] = in_results
    results["out_sample"] = out_results

    sig_in = set(in_results[in_results["significant"]]["characteristic"])
    sig_out = set(out_results[out_results["significant"]]["characteristic"])
    results["significant_in_sample"] = sorted(sig_in)
    results["significant_out_sample"] = sorted(sig_out)
    results["replicated"] = sorted(sig_in & sig_out)
    results["lost_out_of_sample"] = sorted(sig_in - sig_out)
    results["gained_out_of_sample"] = sorted(sig_out - sig_in)

    threshold_tests = {}
    for frac in [0.05, 0.1, 0.15, 0.2]:
        thresh_results = compare_characteristics(chars_df, alpha=alpha)
        sig = set(thresh_results[thresh_results["significant"]]["characteristic"])
        threshold_tests[f"top_{frac:.0%}"] = sorted(sig)
    results["threshold_sensitivity"] = threshold_tests
    core = set(threshold_tests.get("top_10%", []))
    stable = core
    for k, v in threshold_tests.items():
        stable = stable & set(v)
    results["threshold_stable"] = sorted(stable)

    perm_results = {}
    for feat in results.get("replicated", [])[:5]:
        p_perm = permutation_test(chars_df, feat, n_permutations=200)
        perm_results[feat] = p_perm
    results["permutation_tests"] = perm_results

    if index_data is not None:
        regimes = regime_split(chars_df, index_data)
        regime_feat = {}
        for regime_name, regime_df in regimes.items():
            if len(regime_df) < 100:
                continue
            reg_results = compare_characteristics(regime_df, alpha=alpha)
            sig = set(reg_results[reg_results["significant"]]["characteristic"])
            regime_feat[regime_name] = sorted(sig)
        results["regime_stability"] = regime_feat
        if results.get("replicated"):
            core_set = set(results["replicated"])
            all_regimes = [set(v) for v in regime_feat.values()]
            if all_regimes:
                common = core_set
                for r in all_regimes:
                    common = common & r
                results["regime_surviving"] = sorted(common)
            else:
                results["regime_surviving"] = []
        else:
            results["regime_surviving"] = []

    return results


def print_validation_report(results: dict):
    print(f"\n{'='*70}")
    print(f"VALIDATION REPORT")
    print(f"{'='*70}")
    print(f"In-sample observations: {results['n_in_sample']}")
    print(f"Out-of-sample observations: {results['n_out_sample']}")

    print(f"\n--- In-Sample Discovery ---")
    print(f"Significant characteristics: {len(results['significant_in_sample'])}")
    for f in results['significant_in_sample'][:10]:
        row = results["in_sample"][results["in_sample"]["characteristic"] == f].iloc[0]
        print(f"  {f}: d={row['cohens_d']:.4f}, p_corr={row['p_corrected']:.4f}")

    print(f"\n--- Out-of-Sample Replication ---")
    print(f"Replicated: {len(results['replicated'])}")
    for f in results['replicated']:
        row = results["out_sample"][results["out_sample"]["characteristic"] == f].iloc[0]
        print(f"  {f}: d={row['cohens_d']:.4f}, p_corr={row['p_corrected']:.4f}")
    print(f"Lost OOS: {results['lost_out_of_sample']}")
    print(f"Gained OOS: {results['gained_out_of_sample']}")

    print(f"\n--- Threshold Sensitivity ---")
    for k, v in results['threshold_sensitivity'].items():
        print(f"  {k}: {len(v)} significant - {v[:5]}")
    print(f"  Stable across all thresholds: {len(results['threshold_stable'])} - {results['threshold_stable']}")

    if results.get("permutation_tests"):
        print(f"\n--- Permutation Tests ---")
        for feat, p_val in results["permutation_tests"].items():
            print(f"  {feat}: permutation p={p_val:.4f}")

    if results.get("regime_stability"):
        print(f"\n--- Regime Stability ---")
        for regime, feats in results["regime_stability"].items():
            print(f"  {regime}: {len(feats)} significant - {feats[:5]}")
        print(f"  Surviving in all regimes: {results['regime_surviving']}")

    passed = len(results.get("replicated", [])) >= 1
    print(f"\n{'='*70}")
    print(f"VALIDATION: {'PASSED' if passed else 'INCONCLUSIVE'}")
    print(f"{'='*70}")
    return passed


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
