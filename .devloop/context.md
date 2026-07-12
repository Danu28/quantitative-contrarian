# Project Context

## Requirement
Eliminate over-engineering across the repo based on ponytail audit findings. Simplify, delete dead code, consolidate duplicates, extract shared patterns.

## Audit Findings (ranked)
1. **delete:** `backtest_momentum.py` — standalone momentum backtest duplicating `src/backtest.py` framework
2. **delete:** `research_winner_characteristics.py` — superseded by `src/research.py` + `research.py` CLI
3. **shrink:** 7 copies of "load data → filter by cutoff → build dict". Extract `load_symbol_data()` in `db.py`
4. **shrink:** `validate_forward.py:generate_html()` embeds own CSS duplicate of `reporting.py:TEMPLATE_CSS`
5. **yagni:** `REGIME_MULTIPLIERS` in `config.py` — all 1.0, dead config
6. **shrink:** `Portfolio.get_performance()` duplicates `compute_metrics()`
7. **stdlib:** Regime classification in 3 places — consolidate
8. **shrink:** `get_characteristic_names()` hardcodes column names — derive from function output
9. **shrink:** Gate-checking repeated in 3 places
10. **shrink:** `run_backtest.py` duplicates `backtest.py`
11. **shrink:** misplaced import in `reporting.py:528`

## Tech Stack
- Python 3.10+ (pandas, numpy, yfinance, scipy)

## Goals
- Delete dead/superseded files
- Eliminate duplicated patterns
- Consolidate regime classification
- Remove dead config
- Zero behavioral changes
