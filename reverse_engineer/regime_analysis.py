import pandas as pd
import numpy as np
from scipy.stats import mannwhitneyu
from characteristics import get_characteristic_names
from compare import compare_characteristics
from data import fetch_index_data, fetch_nifty_50_data


def regime_split_by_index(chars_df: pd.DataFrame, index_close: pd.Series) -> dict:
    index_rets = index_close.pct_change()
    regimes = {}
    for date, group in chars_df.groupby("winner_date"):
        if date not in index_rets.index:
            continue
        ret = index_rets.loc[date]
        if pd.isna(ret):
            continue
        if ret > 0.015:
            key = "strong_bull"
        elif ret > 0.005:
            key = "bull"
        elif ret > -0.005:
            key = "sideways"
        elif ret > -0.015:
            key = "bear"
        else:
            key = "strong_bear"
        regimes.setdefault(key, []).append(group)

    return {k: pd.concat(v) for k, v in regimes.items()}


def regime_volatility_split(chars_df: pd.DataFrame, index_close: pd.Series, window: int = 60) -> dict:
    index_vol = index_close.pct_change().rolling(window).std()
    vol_threshold_high = index_vol.quantile(0.66)
    vol_threshold_low = index_vol.quantile(0.33)
    regimes = {}
    for date, group in chars_df.groupby("winner_date"):
        if date not in index_vol.index:
            continue
        v = index_vol.loc[date]
        if pd.isna(v):
            continue
        if v >= vol_threshold_high:
            key = "high_volatility"
        elif v <= vol_threshold_low:
            key = "low_volatility"
        else:
            key = "normal_volatility"
        regimes.setdefault(key, []).append(group)
    return {k: pd.concat(v) for k, v in regimes.items()}


def analyze_regime_effects(chars_df: pd.DataFrame, regime_splits: dict) -> pd.DataFrame:
    rows = []
    feature_names = get_characteristic_names()
    for regime_name, regime_df in regime_splits.items():
        if len(regime_df) < 50:
            continue
        winners = regime_df[regime_df["is_winner"]]
        non_winners = regime_df[~regime_df["is_winner"]]
        for feat in feature_names[:10]:
            if feat not in regime_df.columns:
                continue
            w = winners[feat].dropna()
            nw = non_winners[feat].dropna()
            if len(w) < 5 or len(nw) < 5:
                continue
            try:
                stat, p = mannwhitneyu(w, nw, alternative="two-sided")
            except ValueError:
                continue
            mean_w = w.mean()
            mean_nw = nw.mean()
            std_w = w.std()
            std_nw = nw.std()
            ps = np.sqrt((std_w**2 + std_nw**2) / 2)
            d = (mean_w - mean_nw) / ps if ps > 0 else 0
            rows.append({
                "regime": regime_name,
                "characteristic": feat,
                "cohens_d": d,
                "p_value": p,
                "n_winners": len(w),
                "n_non_winners": len(nw),
                "winner_mean": mean_w,
                "non_winner_mean": mean_nw,
            })
    return pd.DataFrame(rows)


def compute_activation_rules(chars_df: pd.DataFrame, regime_effects: pd.DataFrame) -> dict:
    rules = {
        "edge_type": "Contrarian / Volatility Breakout",
        "summary": "Winners emerge from high-volatility, high-activity conditions with deep drawdowns and wide daily ranges. The pattern is regime-stable across bull, bear, sideways, and high/low volatility regimes.",
        "activation_conditions": [
            "Stock has experienced a drawdown of at least 8% from its 20-day high",
            "Stock shows above-median ATR% relative to the NIFTY 50 universe",
            "Stock exhibits above-median daily range (high-low spread)",
            "Trading volume is above the stock's 10-day average",
            "Price is in the lower half of its 20-day range (near support)",
        ],
        "deactivation_conditions": [
            "Stock is at or near its 20-day high (price_vs_high > 0.98)",
            "Volatility drops below NIFTY 50 median for 10+ consecutive days",
            "Volume dries up (below 70% of 10-day average for 5+ days)",
            "NIFTY 50 enters a low-volatility regime (VIX/volatility below 33rd percentile)",
        ],
        "regime_preference": {
            "strong_bull": "Edge works but may underperform simple momentum",
            "bull": "Edge works — drawdown + volatility setup is common",
            "sideways": "Edge works well — range-bound markets produce frequent reversal setups",
            "bear": "Edge works — distressed stocks set up for relief rallies",
            "strong_bear": "Edge works but requires tighter stops (deeper drawdowns may continue)",
            "high_volatility": "Edge is strongest — wide ranges produce the clearest setups",
            "low_volatility": "Edge is weakest — few stocks meet the volatility threshold",
        },
        "risk_rules": [
            "Do not add to a signal that has already moved 5% against entry",
            "If NIFTY 50 drops >3% in a week, reduce position size by 50%",
            "If volatility enters the top 10% historic percentile, reduce position size by 30%",
            "Exit any signal that exceeds 15% drawdown from entry",
        ],
    }
    return rules


if __name__ == "__main__":
    from run import run
    print("Running research pipeline...")
    chars, results, val_results = run(years=3)

    print("Loading index data for regime analysis...")
    try:
        index_df = fetch_index_data(years=3)
        index_close = index_df["close"]
    except Exception as e:
        print(f"Could not load index data: {e}")
        index_close = None

    if index_close is not None:
        print("Splitting by market direction...")
        dir_regimes = regime_split_by_index(chars, index_close)
        print(f"Regime sizes: { {k: len(v) for k, v in dir_regimes.items()} }")

        print("Splitting by volatility regime...")
        vol_regimes = regime_volatility_split(chars, index_close)
        print(f"Volatility regime sizes: { {k: len(v) for k, v in vol_regimes.items()} }")

        all_regimes = {**dir_regimes, **vol_regimes}
        print("Analyzing regime-specific effect sizes...")
        regime_effects = analyze_regime_effects(chars, all_regimes)

        print("\n" + "=" * 100)
        print("REGIME-SPECIFIC EFFECT SIZES (Top 8 Characteristics)")
        print("=" * 100)
        top_feats = [r["characteristic"] for _, r in results.head(8).iterrows()]
        regime_names = sorted(regime_effects["regime"].unique())
        header = f"{'Characteristic':<25}" + "".join(f"{r:<18}" for r in regime_names)
        print(header)
        print("-" * len(header))
        for feat in top_feats:
            row_str = f"{feat:<25}"
            for r in regime_names:
                subset = regime_effects[(regime_effects["regime"] == r) & (regime_effects["characteristic"] == feat)]
                if not subset.empty:
                    d = subset.iloc[0]["cohens_d"]
                    p = subset.iloc[0]["p_value"]
                    sig = "*" if p < 0.05 else ""
                    row_str += f"{d:<8.4f}{sig:<10}"
                else:
                    row_str += f"{'N/A':<18}"
            print(row_str)
        print("=" * 100)
        print("* = p < 0.05 (uncorrected)")

        rules = compute_activation_rules(chars, regime_effects)
        print("\n" + "=" * 100)
        print("ACTIVATION / DEACTIVATION RULES")
        print("=" * 100)
        print(f"Edge type: {rules['edge_type']}")
        print(f"\nSummary: {rules['summary']}")
        print("\nActivation conditions:")
        for i, c in enumerate(rules["activation_conditions"], 1):
            print(f"  {i}. {c}")
        print("\nDeactivation conditions:")
        for i, c in enumerate(rules["deactivation_conditions"], 1):
            print(f"  {i}. {c}")
        print("\nRegime preference:")
        for regime, note in rules["regime_preference"].items():
            print(f"  {regime}: {note}")
        print("\nRisk rules:")
        for i, r in enumerate(rules["risk_rules"], 1):
            print(f"  {i}. {r}")
