# quantitative-contrarian

Statistical contrarian system for Indian equities. Scans any universe for beaten-down stocks near 20-day lows with above-average volatility and volume.

## Entry (6-condition AND gate)

| Condition | Threshold | Purpose |
|-----------|-----------|---------|
| Drawdown | ≤ -5% | Beaten down from 20d high |
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

Research-weighted percentile rank of 8 features with empirically calibrated weights:
- Positive: gap_frequency (0.19), avg_true_range_pct (0.18), avg_up_day (0.17), volatility (0.12)
- Negative (inverted): price_vs_ma10 (0.17), price_vs_high (0.16), ma_slope_5 (0.17), ret_3d (0.13)

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

## Automated Daily Scan

A GitHub Actions workflow runs the daily scan every morning at **9:00 AM IST** and deploys the HTML report to **GitHub Pages**.

### Setup (one-time)

1. **Enable GitHub Pages**: Go to repo **Settings → Pages → Source: "Deploy from a branch"**, branch: `gh-pages`, folder: `/ (root)`. Click Save.
2. **Push to main**: The first push triggers a workflow run.
3. **Bookmark the report**: `https://<your-username>.github.io/ai-quantitative-researcher/latest.html`

### Live report

| Report | URL |
|--------|-----|
| Latest | [https://danu28.github.io/quantitative-contrarian/latest.html](https://danu28.github.io/quantitative-contrarian/latest.html) |
| Historical | `https://danu28.github.io/quantitative-contrarian/daily-scan-YYYY-MM-DD.html` |

Example: [https://danu28.github.io/quantitative-contrarian/daily-scan-2026-07-08.html](https://danu28.github.io/quantitative-contrarian/daily-scan-2026-07-08.html)

Browse all past reports on the `gh-pages` branch: [https://github.com/Danu28/quantitative-contrarian/tree/gh-pages](https://github.com/Danu28/quantitative-contrarian/tree/gh-pages)

### Manual trigger

```bash
# Go to Actions → Daily Scan → Run workflow
# Optionally override universe or date
```

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`
