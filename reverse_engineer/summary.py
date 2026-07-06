from run import run

chars, results, val_results = run(years=3)
rep = val_results["replicated"]

print()
print("=" * 90)
print("WINNER PROFILE — Validated Pre-Move Characteristics")
print("=" * 90)
print(f"{'Characteristic':<25} {'d':<8} {'Dir':<10} {'p_corr':<10} {'Interpretation'}")
print("-" * 90)

interpretations = {
    "avg_true_range_pct": "Wider daily ranges before the move",
    "volatility": "More volatile price action before winning",
    "avg_up_day": "Larger up-day moves in pre-period",
    "gap_frequency": "More frequent 2%+ daily gaps",
    "avg_down_day": "Also larger down days (wider swings both ways)",
    "max_drawdown": "Deeper drawdown from high before reversal",
    "price_vs_low": "Bouncing off recent lows (near support)",
    "max_return": "Higher peak within pre-move window",
}

for f in rep:
    row = results[results["characteristic"] == f].iloc[0]
    w_m = row["winner_mean"]
    nw_m = row["non_winner_mean"]
    d = row["cohens_d"]
    p = row["p_corrected"]
    direction = "+" if w_m > nw_m else "-"
    note = interpretations.get(f, "")
    print(f"{f:<25} {d:<8.4f} {direction:<10} {p:<10.4f} {note}")

print("-" * 90)
print(f"Regime-surviving: {val_results['regime_surviving']}")
print(f"Threshold-stable: {val_results['threshold_stable'][:8]}...")
print(f"OOS replication: {len(rep)} / 26 characteristics")
print("=" * 90)
print()
print("PATTERN SUMMARY:")
print("  Winners emerge from HIGH VOLATILITY + HIGH ACTIVITY conditions,")
print("  not from quiet trending conditions.")
print("  Pre-winner signature: wide ranges, large gaps, deep drawdown,")
print("  elevated volume, price near recent lows.")
print("  This suggests a contrarian / volatility-breakout pattern.")
