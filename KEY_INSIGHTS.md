# Key Insights & Improvement Roadmap

*Generated: 2026-07-06*

---

## 1. System Architecture — How It Works

### Data Layer (`data.py`)
- Fetches OHLCV from Yahoo Finance for NIFTY 50 constituents
- Caches to Parquet for incremental updates
- 48 stocks (TATAMOTORS missing), auto_adjust=True for corporate actions

### Research Layer (`characteristics.py`)
- Computes 26 rolling characteristics per stock (20-day window default)
- ~half are volatility/price-action metrics, ~quarter volume, ~quarter momentum

### Signal Generation (`signal_generator.py`)
- 7 hard-coded entry conditions with fixed thresholds
- Conviction scoring: simple linear combination (max_drawdown×1 + atr×10 + vol×50 + gap_freq×2 + price_vs_low×1)
- Universe-relative: compares each stock to NIFTY 50 median ATR and volatility

### Portfolio Simulation (`portfolio.py`)
- Full position lifecycle: entry, stops (hard/time/trail/profit targets), rebalance
- Weekly rebalance on Fridays only
- Sizing: equal weight with cash buffer (MIN_POSITIONS=3)
- 15% max drawdown disable

### Backtest Engine (`backtest_engine.py`)
- Runs portfolio simulation across configurable horizons
- Generates comprehensive metrics report

### Forward Check (`forward_check.py`)
- Point-in-time signal accuracy test (no trading simulation)
- HTML report output

---

## 2. Current Performance Summary

| Horizon | CAGR | MaxDD | Sharpe | Win Rate | Profit Factor | Trades |
|---------|------|-------|--------|----------|--------------|--------|
| 5d | 3.21% | -3.75% | -0.62 | 63.3% | 2.12 | 60 |
| 10d | 3.92% | -7.77% | -0.34 | 56.2% | 1.68 | 137 |
| 21d | 3.25% | -6.66% | -0.38 | 55.3% | 1.40 | 215 |

All CAGRs below 6.5% risk-free rate → negative Sharpe across the board. Edge exists but too modest for standalone deployment.

---

## 3. Optimization Opportunities

### A. Entry Conditions — Threshold Tuning

**Current:** All 7 entry conditions use fixed, non-optimized thresholds:
- drawdown ≤ -8%
- ATR% > universe median
- volatility > universe median
- gap_frequency > 5%
- price_vs_low < 1.05
- volume_vs_ma10 > 1.0
- price_vs_high < 0.98 (invalidation)

**Problems:**
- These thresholds were set from the RESEARCH winner profile (top 10% stocks), not optimized for the STRATEGY (which has stops, sizing, slippage)
- `volume_vs_ma10 > 1.0` is the most restrictive condition (only 4/48 stocks pass on typical days), yet avg_volume was one of the 3 characteristics that FAILED OOS replication
- The signal count is LOW: on most Fridays 0-1 signals, max ~7

**What to try:**
1. Relax or remove volume condition (it failed OOS)
2. Grid-search drawdown threshold: try -6%, -10%, -12%
3. Replace universe-median comparisons with percentile-based thresholds (top 30% instead of above median)
4. Remove the `price_vs_high < 0.98` invalidation — it may be redundant with `price_vs_low < 1.05`

### B. Conviction Scoring

**Current:**
```python
dd * 1 + atr * 10 + vol * 50 + gap * 2 + (1.05 - pvl) * 1
```

**Problems:**
- The weights are arbitrary (no optimization, no normalization)
- volume_vs_ma10 not included despite being an entry condition
- price_vs_high not included despite being an invalidation condition
- All characteristics should be z-score normalized before weighting

**What to try:**
1. Z-score normalize each characteristic to N(0,1) before combining
2. Use Cohen's d from research as weights (empirically validated): ATR=0.27, gap=0.19, vol=0.19, drawdown=0.11
3. Add volume as a negative weight (it failed OOS — may conflict)

### C. Exit Rules — The Biggest Leak

**Current exit breakdown (21d horizon):**
| Reason | % of Trades | Avg PnL |
|--------|------------|---------|
| not_in_universe | **92%** | +0.96% |
| hard_stop | 4% | -9.21% |
| time_stop | 4% | -0.35% |

**Critical problem:** 92% of exits are "not_in_universe" — positions are closed on the next Friday rebalance simply because the stock is no longer in the signal list. This means:
- The strategy can't hold through the full 20-day horizon for most positions
- Positions are exited prematurely even when they're still working
- This is effectively a 5-day hold (weekly recheck), not a 20-day hold

**What to try:**
1. Remove "not_in_universe" exit — let positions run to time_stop
2. Or change to: exit only if entry conditions are violated by >50% (not just absent)
3. Or: hold to time_stop regardless, unless hard_stop/profit_target hit first

### D. Rebalance Frequency

**Current:** Weekly on Fridays only

**Problem:** Signals are generated every day but entries only happen on Friday. If a stock sets up on Monday, it must wait 4 days. The stock may have already reversed by Friday.

**What to try:**
1. Daily rebalance (enter as soon as conditions met)
2. Semi-weekly (Wednesday + Friday)
3. Or: enter immediately but limit to 2 entries per week to control turnover

### E. Position Sizing

**Current:** Equal weight with cash buffer

**What to try:**
1. Conviction-weighted sizing: allocate more capital to higher conviction scores
2. Volatility-adjusted: smaller positions for high-vol stocks (risk parity)
3. Kelly fraction: size based on win rate and avg win/loss ratio

### F. Cost Sensitivity

**Current model:**
- Slippage: 0.1%
- Brokerage: 0.05%
- These are optimistic for Indian markets (actual brokerage may be 0.01-0.03% for discount brokers, but STT adds ~0.1% per side)

**What to try:**
- Model actual Indian brokerage: 0.01% + STT 0.1% + GST + SEBI charges ≈ 0.15% per side
- Test with 0.2% slippage for less liquid NIFTY 50 names
- Include bid-ask spread (0.05-0.15% for NIFTY 50)

---

## 4. Structural Improvements

### A. Survivorship Bias Fix

**Current:** Only tracks current NIFTY 50 constituents. Stocks that were delisted or removed during the backtest period are missing.

**Impact:** Overstates performance — removed stocks are often poor performers.

**Fix:** Fetch NIFTY 50 historical constituent list from NSE or an API, include stocks that were in the index at each point in time.

### B. Index-Relative Returns

**Current:** Winner definition is absolute return, not benchmark-relative.

**Problem:** During strong bull markets, many stocks are "winners" regardless of the strategy. The edge may be weaker when benchmark-adjusted.

**Fix:** Re-run research with benchmark-relative returns (stock return − NIFTY 50 return). This would filter out market-beta and reveal the true alpha signal.

### C. Data Quality

**Current:** Yahoo Finance auto_adjust=True, which adjusts historical prices for dividends and splits.

**Problem:** auto_adjust can introduce artifacts — especially for stocks with large dividends. The adjusted close may not reflect actual tradeable prices.

**Fix:** Use raw close + separate dividend adjustment, or cross-check with NSE data.

### D. Feature Engineering

**Current:** 26 rolling characteristics, all based on OHLCV only.

**Missing features to add:**
- RSI (relative strength index) — standard mean-reversion signal
- Bollinger Band position (%B) — how far price is from moving average
- ATR ratio (current ATR / 50-day ATR) — volatility expansion/contraction
- Volume-adjusted price change (VWAP deviation)
- Sector-relative returns (is the stock weak vs its sector?)
- Delivery volume % (if available) — shows conviction in moves
- Put/Call ratio of the stock (if available) — sentiment signal
- Distance from 200-day MA — long-term trend context

### E. Machine Learning Integration

**Current:** Hard-coded rules with fixed thresholds.

**What's possible:**
1. **Logistic Regression** — learn optimal decision boundary for winner classification using the 8 validated characteristics as features. Very interpretable, low overfitting risk.
2. **Random Forest / XGBoost** — only if linear model is empirically beaten (per the original design principle). Can capture non-linear interactions (e.g., drawdown × volatility interaction).
3. **Ensemble** — combine rule-based + ML signals with a simple voting mechanism.

**Caution:** The current dataset has only ~81K observations with ~26 features. ML requires careful cross-validation to avoid overfitting. Start with logistic regression.

---

## 5. New Strategy Possibilities

### A. Long-Short Extension

**Current:** Long-only.

**What if:** The research also identifies LOSER characteristics (bottom 10% forward return). If losers show a consistent opposite profile, a short book could be added.

**Potential benefit:** Market-neutral returns, uncorrelated to NIFTY 50. Sharpe could double.

**Risk:** Short selling in India requires margins, harder to execute, unlimited loss potential.

### B. Sector Rotation Extension

**Current:** Stock-level signals within entire universe.

**What if:** The edge works better in specific sectors (IT, Auto, Metals showed strong signals). A sector-level overlay could improve hit rate.

**Implementation:**
1. Compute sector-level signal density (which sectors have the most qualifying stocks)
2. Overweight sectors with high signal density
3. Skip sectors with no signals

### C. Multi-Factor Ensemble

**Current:** Single factor (volatility contrarian).

**What if:** Combine with independent factors:
- **Momentum factor** (when our signal is absent but momentum is strong)
- **Value factor** (low P/E stocks in drawdown)
- **Low-vol factor** (when market is risk-off)

**Implementation:** Simple voting: if 2 of 3 factors agree, take the signal. This is a real institutional approach (e.g., Goldman's "conviction basket").

### D. Options-Based Strategy

**Current:** Spot trading only.

**What if:** Instead of buying the stock, buy a 4-week call option when the signal fires. This would:
- Limit downside to the option premium
- Provide leverage (higher returns if right)
- Be natural for the contrarian/reversal profile

**Requires:** Options data feed, options pricing model, margin account.

---

## 6. Quick Wins (Low Effort, High Impact)

| # | Change | Expected Impact | Effort |
|---|--------|----------------|--------|
| 1 | Remove `not_in_universe` exit — hold to time_stop | +1-2% CAGR (let winners run) | 1 line |
| 2 | Daily rebalance (not just Fridays) | +more signals, less missed setups | 1 line |
| 3 | Remove volume condition (failed OOS) | +more signals, +diversification | 1 line |
| 4 | Z-score normalize conviction weights | Better signal ranking | 10 lines |
| 5 | Add RSI as entry filter (RSI < 35) | Avoid buying extended down moves | 5 lines |
| 6 | Cross-check Sharpe with raw data (not auto_adjust) | Higher confidence in results | 1 line |
| 7 | Test with realistic Indian brokerage (0.15% per side) | Realistic cost estimate | 5 lines |

---

## 7. Fundamental Limitation

> **The core issue is signal scarcity.** With 48 stocks, top 10% winner definition gives ~5 winners per day. The 7 entry conditions filter this down to 0-3 signals per day. With weekly rebalance and "not_in_universe" exits, most positions last only 5 days instead of 20.

**To move from 3-4% CAGR to institutional-grade (8-15%):**
1. Expand universe to NIFTY 500 (10x more candidates)
2. Relax volume condition (it failed OOS anyway)
3. Hold positions to time_stop (let the full horizon play out)
4. Add conviction-weighted sizing

These four changes together could realistically double the CAGR to 6-8%.

---

## 8. How to Verify Improvements

Each optimization should be tested as a hypothesis:

1. Change ONE variable at a time
2. Run backtest_engine.py
3. Compare CAGR, MaxDD, Sharpe, Trades to baseline
4. Only keep changes that improve without increasing MaxDD >15%
5. Run forward_check.py on 5 random historical dates to spot-check

This avoids the optimization bias trap.

---

## 9. Decision Matrix

| Approach | Expected CAGR | Risk | Complexity | Time to Implement |
|----------|--------------|------|-----------|-------------------|
| Current baseline | 3-4% | Low | Low | Already done |
| Fix exits + rebalance | 5-6% | Low | Low | 1 day |
| + Expand to NIFTY 500 | 6-8% | Medium | Medium | 1 week |
| + ML scoring | 7-10% | Medium-High | Medium | 2 weeks |
| + Long-short | 10-15% | High | High | 1 month |
| + Options overlay | 15-25% | Very High | Very High | 2-3 months |

**Recommended path:** Quick wins first (exits, rebalance, volume, z-score) → NIFTY 500 expansion → ML only if linear improvement is needed.
