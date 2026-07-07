# Dev Loop Context

## Project
AI Quantitative Researcher — contrarian system for Indian equities (NIFTY 50)

## Current Cycle
Create master interactive batch file (`run.bat`) that wraps all CLI tools.

## Key Files
- `daily_scan.py` — CLI tool for daily signal scan
- `forward_check.py` — CLI tool for forward return check
- `src/backtest.py` — backtest engine (run via `backtest.py` or direct)
- `run.bat` — master launcher (TO BE CREATED)

## Requirements
- Windows batch file (.bat)
- Interactive menu with numbered options
- Prompts for all parameters with sensible defaults
- Options: Daily Scan, Forward Check, Backtest, Run All
- Color-coded menu (optional)
- Clear error handling
- Opens HTML reports when generated

## Stack
Windows batch (.bat), Python 3.14

## Validation
Run `run.bat`, select each option, verify it works.
