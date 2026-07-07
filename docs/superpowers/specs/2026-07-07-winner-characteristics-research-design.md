# Winner Characteristics Research Pipeline

## Problem

The current strategy uses an AND-gate (drawdown, volume, ATR, price vs low/high) to filter candidates, then a weighted ranking to select the best pick. The ranking was built from research on features predictive of returns *within the AND-gate universe*.

**Unknown:** Across the entire universe, what characteristics actually identify stocks that become the biggest winners over 5d and 10d horizons? The current entry gates may align with these characteristics — or they may exclude the actual winners.

## Goal

Build a reusable research pipeline that, for any forward horizon:
1. Computes forward returns for all stocks on each sample date
2. Labels the top decile as "winners"
3. Quantifies which characteristics distinguish winners from non-winners
4. Reports effect sizes, quintile win rates, and monotonicity

## Design

### Scope

A single standalone script: `research_winner_characteristics.py`

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--horizon` | 5 | Forward trading days (5, 10, 20) |
| `--universe` | niftymidcap150 | Universe slug |
| `--years` | 3 | Years of history |
| `--top-pct` | 10 | Top % of stocks labeled as winners |
| `--sample-interval` | 5 | Sample every N trading days |

### Algorithm

1. Load universe symbols and OHLCV data from SQLite
2. Precompute all 21+ characteristics for each stock (via `precompute_all_characteristics`)
3. Determine sample dates: every `sample_interval`-th trading day, excluding the last `horizon` days (need forward data)
4. For each sample date:
   a. For each stock with data, compute forward return at `horizon` trading days
   b. Sort all stocks by forward return, label top `top_pct`% as "winners" (1) vs rest (0)
   c. Append each stock's characteristics + winner label to aggregate dataset
5. After all dates processed, for each characteristic:
   a. Compute mean(winners) vs mean(non-winners), difference
   b. Cohen's d = (mean_diff) / pooled_std
   c. Sort stocks into quintiles by characteristic value → compute win rate in each quintile
   d. Check monotonicity: is win rate strictly increasing/decreasing across Q1→Q5?
6. Print sorted table by |Cohen's d| descending
7. Print per-quintile win rates for top characteristics
8. Print comparison against current AND-gate conditions

### Output Format

**Table 1 — Characteristics ranked by effect size**
```
Characteristic        Winners  Non-Win  Diff     Cohen_d  Quintile_WR
avg_true_range_pct    +3.12%   +1.04%   +2.08%   0.42     Q1:42% Q2:48% Q3:52% Q4:58% Q5:63%
price_vs_ma10         +0.98    +1.03    -0.05     -0.31    Q1:61% Q2:55% Q3:50% Q4:46% Q5:39%
...
```

**Table 2 — Quintile win rates (top 5 characteristics)**
```
                    Q1(low)  Q2      Q3      Q4      Q5(high)  Monotonic
avg_true_range_pct  42.1%   47.8%   52.3%   58.0%   62.9%     Yes ↑
```

**Table 3 — AND-gate alignment check**
```
AND-gate condition   Direction   Winner char direction   Aligned?
dd < -5%             negative    max_drawdown: d=-0.15   ✓ partial
volume_vs_ma10 > 1   positive    volume_vs_ma10: d=+0.08  ✓ weak
...
```

### Dependencies

- Uses existing `src/db.py`, `src/features.py` — zero new dependencies
- Follows same pattern as `forward_check.py`, `validate_forward.py`

### Constraints

- No modification to existing files
- No new dependencies
- Script must run standalone: `python research_winner_characteristics.py --horizon 5`
- Runtime target: < 5 minutes for full 3-year sample (every 5th day)

## Success Criteria

The script produces actionable output that answers:
1. Which 3-5 characteristics most strongly separate winners from non-winners?
2. Are the AND-gate conditions aligned with these characteristics?
3. Does the relationship hold across both 5d and 10d horizons?
4. Is the relationship monotonic (more extreme = better) or threshold-based?
