# quantitative-contrarian

Statistical contrarian system for Indian equities. Scans any universe for beaten-down stocks near 20-day lows with above-average volatility and volume.

## Entry (6-condition AND gate)

| Condition | Threshold | Purpose |
|-----------|-----------|---------|
| Drawdown | ≤ -8% | Beaten down from 20d high |
| Price vs Low | < 1.05 | Near 20-day low |
| Price vs High | < 0.98 | Not at 20-day high |
| Volume vs MA(10) | > 1.0 | Above-average volume |
| ATR | > universe median | Above-average range |
| Volatility | > universe median | Above-average risk |

## Exit Rules

- **Target 1** — +12% from entry (sell half)
- **Target 2** — +18% from entry (sell remainder)
- **Hard Stop** — -8% from entry
- **Trailing Stop** — activates at +10%, trails at 12%
- **Time Stop** — exit after 20 trading days

## Conviction

Equal-weight percentile rank of 5 features (drawdown, ATR, volatility, price-vs-low distance, volume ratio). No arbitrary multipliers.

## Data

OHLCV cached in SQLite via yfinance. Single source of truth. Three universe configs:

| Universe | File | Stocks |
|----------|------|--------|
| NIFTY 50 | `universe/nifty50.json` | 50 |
| NIFTY 500 | `universe/nifty500.json` | 500 |
| NIFTY Midcap 150 | `universe/niftymidcap150.json` | 150 |

## CLI Tools

| Command | Description |
|---------|-------------|
| `backtest.py` | Historical simulation with costs, multiple horizons, full metrics |
| `daily_scan.py` | Today's actionable signals with exit levels, regime context, HTML report |
| `forward_check.py` | Forward return check for any date/universe, HTML report |
| `fetch.py` | Download/cache/validate data for any universe |
| `research.py` | Statistical research pipeline (Mann-Whitney, Bonferroni, permutation tests) |

## Project Structure

| File | Purpose |
|------|---------|
| `src/db.py` | SQLite R/W, yfinance fetch, universe loading |
| `src/features.py` | 26 rolling characteristics per stock |
| `src/backtest.py` | 6-condition signal generator, Portfolio class, backtest engine |
| `src/research.py` | Statistical validation: compare, split, permute, validate, scan |
| `src/reporting.py` | Beautiful standalone HTML reports (dark/light mode, micro-bars, responsive) |
| `backtest.py` | CLI wrapper for backtest engine |
| `daily_scan.py` | CLI for today's signals with market regime context |
| `forward_check.py` | CLI for forward return checks |
| `fetch.py` | CLI for data fetching and validation |
| `research.py` | CLI for research pipeline |

## Status

Backtested on NIFTY 50 (3yr): **+3.12% CAGR** at 21d horizon, MaxDrawdown **-6.49%**, win rate **55.3%**, profit factor **1.49**.

Not deployment-ready — 87% of exits are "not_in_universe" (signal lost before target hit). Sharpe ratio negative at 6.5% risk-free rate.

## Requirements

- Python 3.10+
- `pip install pandas numpy scipy yfinance`
