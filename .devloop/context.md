# Dev Loop Context

## Project
AI Quantitative Researcher — contrarian system for Indian equities (NIFTY 50)

## Current Cycle
Production hardening: Remove not_in_universe exit in `Portfolio._rebalance()`

## Key Files
- `src/backtest.py` — main backtest engine, Portfolio class, generate_signals
- `backtest.py` — CLI wrapper

## The Fix
In `Portfolio._rebalance()` (src/backtest.py), removed the block that exits positions not in the current signal list. Reason: entry conditions (6-condition AND gate) should not dictate hold conditions. Positions now run to target/stop/time-stop.

## Validation
Backtest (21d): CAGR 3.51% → 3.80%, not_in_universe 92→0, avg hold 8.8→18.6d. All gates pass.

## Stack
Python 3.14, pandas, numpy, scipy, yfinance, SQLite
