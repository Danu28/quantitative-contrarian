import pandas as pd
import numpy as np
from scipy.stats import mannwhitneyu, ttest_ind
from characteristics import get_characteristic_names


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


if __name__ == "__main__":
    from winners import load_all_data, identify_winners, get_pre_move_data
    print("Loading data...")
    data = load_all_data()
    print("Identifying winners...")
    winners = identify_winners(data, horizon=20, top_frac=0.1)
    print("Extracting pre-move windows...")
    instances = get_pre_move_data(data, winners, pre_move_window=20)
    print("Computing characteristics...")
    chars = compute_all_characteristics(instances, pre_move_window=20)
    print("Comparing winners vs non-winners...")
    results = compare_characteristics(chars)
    print_comparison_results(results)
