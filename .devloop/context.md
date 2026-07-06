# DEV-LOOP Context

## Project
AI Quant Researcher — Volatility Contrarian Strategy

## Goal
Build the Volatility Contrarian strategy into a runnable system:
1. `signal_generator.py` — daily signal evaluation using 5 entry conditions
2. `portfolio.py` — position tracking, stops, risk limits
3. `main.py` — daily run loop (fetch data → compute features → evaluate signals → manage positions)
4. `dashboard.py` — Streamlit web UI showing current signals, positions, performance

## Stack
- Python 3.14, pandas, numpy, yfinance, Streamlit
- Parquet data cache (existing `reverse_engineer/`)
- No database, no API keys

## Key Design Decisions
- 20-day horizon (validated as optimal across 5/20/40 day tests)
- 5 entry conditions: drawdown ≥8%, ATR% above median, volume above avg, price in lower 50% range, gap frequency >5%
- Exits: profit target 10%/15%, hard stop 8%, time stop 20d, trailing stop 10%
- Equal weight, max 10 positions, weekly rebalance Friday
- Regime multiplier: 1.0x normal, 0.5x strong bear/low vol

## Source of Truth
- `FINDINGS.md` for complete research and strategy specification
- `reverse_engineer/` for existing research code
- `.orchestrator/state.json` for pipeline stage tracking
