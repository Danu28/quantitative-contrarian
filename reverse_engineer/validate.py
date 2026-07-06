import pandas as pd
import numpy as np
from scipy.stats import mannwhitneyu
from characteristics import get_characteristic_names
from compare import compare_characteristics


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
        print(f"  {k}: {len(v)} significant — {v[:5]}")
    print(f"  Stable across all thresholds: {len(results['threshold_stable'])} — {results['threshold_stable']}")

    if results.get("permutation_tests"):
        print(f"\n--- Permutation Tests ---")
        for feat, p_val in results["permutation_tests"].items():
            print(f"  {feat}: permutation p={p_val:.4f}")

    if results.get("regime_stability"):
        print(f"\n--- Regime Stability ---")
        for regime, feats in results["regime_stability"].items():
            print(f"  {regime}: {len(feats)} significant — {feats[:5]}")
        print(f"  Surviving in all regimes: {results['regime_surviving']}")

    passed = len(results.get("replicated", [])) >= 1
    print(f"\n{'='*70}")
    print(f"VALIDATION: {'PASSED' if passed else 'INCONCLUSIVE'}")
    print(f"{'='*70}")
    return passed
