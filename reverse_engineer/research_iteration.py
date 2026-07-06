import pandas as pd
import numpy as np
from data import fetch_nifty_50_data
from characteristics import precompute_all_characteristics, get_characteristic_names
from compare import compare_characteristics, print_comparison_results


def run_horizon_scan(years=3, horizons=[5, 10, 20, 40], top_frac=0.1):
    print(f"Loading {years} years of NIFTY 50 data...")
    data = fetch_nifty_50_data(years=years)
    print(f"Loaded {len(data)} stocks")

    all_results = {}
    for horizon in horizons:
        print(f"\n{'='*70}")
        print(f"HORIZON: {horizon} trading days")
        print(f"{'='*70}")

        char_data = precompute_all_characteristics(data, window=horizon)

        all_rows = []
        for symbol, df in data.items():
            close = df["close"]
            fwd = close.shift(-horizon) / close - 1
            temp = pd.DataFrame({
                "symbol": symbol, "date": df.index, "fwd_return": fwd,
            })
            all_rows.append(temp)

        combined = pd.concat(all_rows).dropna(subset=["fwd_return"])
        tagged = []
        for date, group in combined.groupby("date"):
            n = len(group)
            n_winners = max(1, int(n * top_frac))
            sg = group.sort_values("fwd_return", ascending=False)
            iw = pd.Series(False, index=sg.index)
            iw.iloc[:n_winners] = True
            sg["is_winner"] = iw.values
            tagged.append(sg)

        all_tagged = pd.concat(tagged)
        n_winners = all_tagged["is_winner"].sum()
        print(f"Observations: {len(all_tagged)}, Winners: {n_winners} ({100*n_winners/len(all_tagged):.1f}%)")

        chars_rows = []
        for _, row in all_tagged.iterrows():
            symbol = row["symbol"]
            date = row["date"]
            if symbol not in char_data:
                continue
            cdf = char_data[symbol]
            try:
                vals = cdf.loc[date].to_dict()
            except KeyError:
                continue
            if pd.isna(vals.get("volatility")):
                continue
            vals["symbol"] = symbol
            vals["winner_date"] = date
            vals["is_winner"] = bool(row["is_winner"])
            vals["fwd_return"] = row["fwd_return"]
            chars_rows.append(vals)

        chars_df = pd.DataFrame(chars_rows)
        for col in chars_df.select_dtypes(include=[np.number]).columns:
            chars_df[col] = chars_df[col].replace([np.inf, -np.inf], np.nan)

        print(f"Characteristic instances: {len(chars_df)}")

        results = compare_characteristics(chars_df)
        print_comparison_results(results)

        top_5 = results.head(5)
        avg_d = top_5["cohens_d"].abs().mean()
        n_sig = results["significant"].sum()
        print(f"Average |d| of top 5: {avg_d:.4f}")
        print(f"Significant characteristics: {n_sig}/{len(results)}")

        all_results[horizon] = {
            "results": results,
            "chars": chars_df,
            "avg_top5_d": avg_d,
            "n_sig": n_sig,
            "n_obs": len(chars_df),
        }

    print(f"\n{'='*70}")
    print(f"HORIZON COMPARISON SUMMARY")
    print(f"{'='*70}")
    print(f"{'Horizon':<10} {'Obs':<10} {'Top5 Avg |d|':<15} {'Significant':<15} {'Top Features'}")
    print(f"{'-'*70}")
    for h in horizons:
        r = all_results[h]
        top_feats = [f"{r['results'].iloc[i]['characteristic']}({r['results'].iloc[i]['cohens_d']:.2f})" for i in range(min(3, len(r['results'])))]
        print(f"{h:<10} {r['n_obs']:<10} {r['avg_top5_d']:<15.4f} {r['n_sig']:<15} {', '.join(top_feats)}")

    return all_results


if __name__ == "__main__":
    results = run_horizon_scan(years=3, horizons=[5, 10, 20, 40])
