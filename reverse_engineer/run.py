import pandas as pd
import numpy as np
from data import fetch_nifty_50_data
from characteristics import precompute_all_characteristics, extract_characteristics, get_characteristic_names
from compare import compare_characteristics, print_comparison_results

HORIZON = 20
TOP_FRAC = 0.1
WINDOW = 20


def run(years: int = 3):
    print(f"Loading {years} years of NIFTY 50 data...")
    data = fetch_nifty_50_data(years=years)
    print(f"Loaded {len(data)} stocks")

    print(f"Pre-computing rolling characteristics (window={WINDOW})...")
    char_data = precompute_all_characteristics(data, window=WINDOW)
    print("Done.")

    print(f"Computing forward returns (horizon={HORIZON} days)...")
    all_rows = []
    for symbol, df in data.items():
        close = df["close"]
        fwd = close.shift(-HORIZON) / close - 1
        temp = pd.DataFrame({
            "symbol": symbol,
            "date": df.index,
            "fwd_return": fwd,
        })
        all_rows.append(temp)

    combined = pd.concat(all_rows).dropna(subset=["fwd_return"])
    print(f"Total observations: {len(combined)}")

    print("Labeling winners (top 10% by forward return)...")
    tagged = []
    for date, group in combined.groupby("date"):
        n = len(group)
        n_winners = max(1, int(n * TOP_FRAC))
        sorted_group = group.sort_values("fwd_return", ascending=False)
        is_winner = pd.Series(False, index=sorted_group.index)
        is_winner.iloc[:n_winners] = True
        sorted_group["is_winner"] = is_winner.values
        tagged.append(sorted_group)

    all_tagged = pd.concat(tagged)
    n_winners = all_tagged["is_winner"].sum()
    print(f"Winner instances: {n_winners} ({100 * n_winners / len(all_tagged):.1f}%)")

    print("Extracting characteristics for all observations...")
    chars_df = extract_characteristics(char_data, all_tagged)
    for col in chars_df.select_dtypes(include=[np.number]).columns:
        chars_df[col] = chars_df[col].replace([np.inf, -np.inf], np.nan)
    print(f"Total characteristic instances: {len(chars_df)}")
    print(f"Winners: {chars_df['is_winner'].sum()}, Non-winners: {(~chars_df['is_winner']).sum()}")

    print("Comparing winners vs non-winners...")
    results = compare_characteristics(chars_df)
    print_comparison_results(results)

    print("Running full validation...")
    from validate import validate, print_validation_report
    try:
        from data import fetch_index_data
        index_df = fetch_index_data(years=years)
        index_series = index_df["close"] if not index_df.empty else None
    except Exception:
        index_series = None
    val_results = validate(chars_df, index_data=index_series)
    print_validation_report(val_results)

    return chars_df, results, val_results


if __name__ == "__main__":
    chars, results, val_results = run(years=3)
