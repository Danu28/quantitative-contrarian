# quantitative-contrarian

Dual-strategy quantitative trading system for Indian equities:
- **Contrarian** — beaten-down stocks near 20-day lows with above-average volatility
- **Momentum** — trailing 12-month return ranking with sector/liquidity/price filters

## Strategies

### Contrarian

6-condition AND gate scanning for oversold reversals:

| Condition | Threshold | Purpose |
|-----------|-----------|---------|
| Drawdown | ≤ -5% | Beaten down from 20d high |
| Price vs Low | < 1.05 | Near 20-day low |
| Price vs High | < 0.98 | Not at 20-day high |
| Volume vs MA(10) | > 1.0 | Above-average volume |
| ATR | > universe median | Above-average range |
| Volatility | > universe median | Above-average risk |

**Exits:** Target1 +12%, Target2 +18%, Hard Stop -8%, Trailing +10%/12%, Time Stop 20d

**Conviction:** Research-weighted percentile rank of 8 features.

### 12-Month Momentum

Ranks universe by trailing 252-session return, applies filters, takes top positions:

| Filter | Setting | Purpose |
|--------|---------|---------|
| Min Volume | ₹10Cr daily | Liquidity |
| Max Price | ₹10,000 | Affordability |
| Min Price | ₹20 | Penny stock avoidance |
| Max per Sector | 2 | Diversification |

**Exits:** Hard Stop -15%, Trailing +20%/20%, monthly rebalance

**Backtest (₹1Cr, 10yr):** CAGR 28.9%, Sharpe 1.41, Max DD -28.3%, Win Rate 56.3%

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
| `daily_scan.py` | Today's signals with exit levels, regime context, HTML report. Use `--strategy contrarian\|momentum` |
| `forward_check.py` | Forward return check for any date/universe. Use `--strategy contrarian\|momentum` |
| `fetch.py` | Download/cache/validate data for any universe |
| `research.py` | Statistical research pipeline (Mann-Whitney, Bonferroni, permutation tests) |
| `run.bat` | Menu-driven launcher for all tools (Windows) |

## Project Structure

| File | Purpose |
|------|---------|
| `src/db.py` | SQLite R/W, yfinance fetch, universe loading |
| `src/features.py` | 26 rolling characteristics per stock |
| `src/backtest.py` | Signal generators (contrarian + momentum), Portfolio class, backtest engine |
| `src/research.py` | Statistical validation: compare, split, permute, validate, scan |
| `src/reporting.py` | Beautiful standalone HTML reports (dark/light mode, micro-bars, responsive) |
| `src/config.py` | All strategy parameters (stop loss, position limits, filters) |
| `backtest.py` | CLI wrapper for backtest engine |
| `daily_scan.py` | CLI for today's signals with market regime context |
| `forward_check.py` | CLI for forward return checks |
| `fetch.py` | CLI for data fetching and validation |
| `research.py` | CLI for research pipeline |
| `docs/index.html` | Static dashboard deployed to GitHub Pages |

## Status

**Contrarian:** Backtested on NIFTY 50 (3yr): +3.12% CAGR, MaxDD -6.49%, win rate 55.3%. Not deployment-ready alone — 87% of exits are "not_in_universe".

**Momentum:** Backtested on Nifty 50 + Midcap 150 (10yr, ₹1Cr): **28.9% CAGR**, Sharpe **1.41**, MaxDD **-28.3%**, Profit Factor **1.60**. Suitable for paper trading. Under ₹1L capital, CAGR drops to 21.9% (trade costs dominate).

## Automated Daily Scan

A GitHub Actions workflow runs both contrarian and momentum scans every morning at **9:00 AM IST** and deploys results to **GitHub Pages**.

### Dashboard

Single-page dashboard aggregating both strategies, backtest summaries, regime reference, and daily reports:

| Resource | URL |
|----------|-----|
| **Dashboard** | [https://danu28.github.io/quantitative-contrarian/](https://danu28.github.io/quantitative-contrarian/) |
| Contrarian Scan | `contrarian-scan-YYYY-MM-DD.html` |
| Momentum Scan | `momentum-scan-YYYY-MM-DD.html` |

The dashboard auto-links to all generated reports. Historical scans live on the `gh-pages` branch: [https://github.com/Danu28/quantitative-contrarian/tree/gh-pages](https://github.com/Danu28/quantitative-contrarian/tree/gh-pages)

### Manual trigger

```bash
# Go to Actions → Daily Scan → Run workflow
# Optionally override universe, date, or strategy
```

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`
