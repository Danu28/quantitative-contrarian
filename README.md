# quantitative-contrarian

Statistical contrarian system for Indian equities. Scans any universe (NIFTY 50, Midcap 150, NIFTY 500) for beaten-down stocks near 20-day lows with above-average volatility and volume.

## How it works

**Entry** — 6-condition AND gate:
- Drawdown ≥ -8%
- Near 20d low
- Not at 20d high
- Volume above average
- ATR above median
- Volatility above median

**Conviction** — Equal-weight percentile rank of 5 features (no arbitrary multipliers)

**Exit** — Target1 +12% (sell half), Target2 +18%, HardStop -8%, Trailing stop (activate +10%, trail 12%), TimeStop 20d

**Output** — Terminal table + beautiful standalone HTML report with regime context, dark/light mode.

## Usage

```bash
python backtest.py --universe nifty50 --years 3
python daily_scan.py --universe niftymidcap150 --output report.html
python forward_check.py --universe nifty50 --horizons 5 10 21 --output fwd.html
python fetch.py --universe nifty500 --validate-only
```

## Data

OHLCV cached in SQLite via yfinance. Single source of truth — no parquet files. Supports any universe via JSON config in `universe/`.

## Project Structure

```
src/db.py          SQLite data layer
src/features.py    26 rolling characteristics
src/backtest.py    Signal generation, portfolio, backtest engine
src/research.py    Statistical validation pipeline
src/reporting.py   Beautiful Reports design system
```

## CLI Tools

| Tool | Purpose |
|------|---------|
| `backtest.py` | Historical simulation with costs, multiple horizons |
| `daily_scan.py` | Today's actionable signals with exit levels, regime context |
| `forward_check.py` | Forward return check for any date/universe with HTML report |
| `fetch.py` | Download/cache/validate data for any universe |
| `research.py` | Statistical research scan (Mann-Whitney, permutation tests) |

## Status

Backtested on NIFTY 50 (3yr): +3.12% CAGR at 21d horizon. Not deployment-ready — 87% of exits are signal loss before target hit. Sharpe negative at 6.5% risk-free rate.
