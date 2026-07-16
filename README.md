# quantitative-contrarian

Quantitative multi-strategy trading system for Indian equities (NIFTY universe).

## Strategy: Factor Model (primary)

4-factor conviction + regime filter for 10-day holding periods:

```
conviction = [ Rank(ret_20d × vol_ratio / vol_20d)
             + Rank(sector_rel_ret)
             + Rank(recovery_ratio / vol_20d)
             + Rank(-days_since_20d_high) ]
           × regime_mult
```

| Signal | Economic mechanism |
|--------|-------------------|
| Risk-adjusted momentum | Returns normalized by volatility, amplified by rising volume |
| Sector-relative return | Strength within sector peers |
| Recovery strength | Bounce from 5d low, disciplined by volatility |
| Freshness | Recent highs → likely continuation (not stale reversal) |
| Regime filter | Tapered exposure when market ret_20d < -5% |

### Performance (NIFTY 50, top 5 picks, 10d hold)

| Metric | 15-date (Mar-Jul 2026) | 1-year (Jul 2025-Jul 2026) |
|--------|----------------------|---------------------------|
| Win rate | 75% | 56% |
| Avg return | +2.03% | +0.89% |
| Max drawdown | -1.95% | -4.36% |

NIFTY Midcap 150: 53% win, +1.37% avg on 15-date (factor doesn't generalize to midcaps well).

## Secondary Strategies

**Contrarian** — 6-condition AND gate for oversold reversals (drawdown ≤ -5%, near 20d low, above-avg volume/volatility).

**Momentum** — 12-month return ranking with liquidity/price/diversification filters.

## Data

OHLCV cached in SQLite via yfinance. Three universes:

| Universe | Slug | Stocks |
|----------|------|--------|
| NIFTY 50 | `nifty50` | 50 |
| NIFTY Midcap 150 | `niftymidcap150` | 150 |
| NIFTY 500 | `nifty500` | 500 |

## CLI Tools

| Command | Description |
|---------|-------------|
| `daily_scan.py` | Today's signals with exit targets, regime, HTML report. `--strategy factor|contrarian|momentum` |
| `forward_check.py` | Historical forward return check. `--date YYYY-MM-DD --strategy factor --top 5 --universe nifty50` |
| `batch_fwd_15.py` | 15-date quick validation. `--universe nifty50` (default) |
| `batch_fwd_1yr.py` | 1-year non-overlapping validation. `--universe nifty50 --year-offset 0` |
| `compare_strategies.py` | Side-by-side factor vs contrarian comparison |
| `validate_forward.py` | Walk-forward validation with portfolio simulation |

## Project Structure

| File | Purpose |
|------|---------|
| `src/factors.py` | Factor signal generation + sector diversification |
| `src/backtest.py` | Signal generators (factor/contrarian/momentum), Portfolio class, backtest engine |
| `src/db.py` | SQLite R/W, yfinance fetch, universe loading |
| `src/features.py` | Rolling stock characteristics computation |
| `src/config.py` | Strategy parameters, regime rules, cost constants |
| `src/reporting.py` | Standalone HTML reports (dark/light mode, responsive) |
| `src/research.py` | Statistical research pipeline (Mann-Whitney, permutation tests) |
| `tests/` | Pytest suite: 57 tests across factor signals, backtest portfolio, features |

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`
