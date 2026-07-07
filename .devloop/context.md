# Dev Loop Context

## Project
AI Quantitative Researcher — contrarian system for Indian equities (NIFTY 50)

## Current Cycle
Complete trader playbook: Add regime-based position sizing recommendations to daily_scan.py and HTML report.

## Key Files
- `daily_scan.py` — CLI tool for daily signal scan
- `src/reporting.py` — HTML report generation
- `TRADER_PLAYBOOK.md` — Complete trader documentation (already written)

## What's Being Built
1. `compute_regime()` in daily_scan.py already computes NIFTY 20d trend.
   Change: add `max_positions` and `action` recommendation to the returned dict.
2. Console output: show regime action (Full/Reduce/Skip) with max position count.
3. HTML report: add regime recommendation section with clear action banner.
4. The regime multiplier logic:
   - Bull (> +3%): 1 position max (Skip or minimal)
   - Sideways (-3% to +3%): 3 positions (Full deploy)
   - Bear/Crash (< -3%): 3 positions (Full deploy — best regime)

## Stack
Python 3.14, pandas, numpy, scipy, yfinance, SQLite

## Validation
python daily_scan.py --output report.html
Verify: regime label, recommended action, max positions displayed correctly.
