# Project Workflow

## Skill Order (in this sequence)

1. **first-principles** — analyze, question, plan before any implementation
2. **dev-loop** — implement changes with state tracking in `.devloop/`
3. **alpha-factor-discovery** — evaluate or improve factor models
4. **beautiful-reports** — generate HTML reports

After dev-loop tasks complete, delete `.devloop/` directory.

## Workflow for Factor Model Changes

### Plan (first-principles)
- Question assumptions, constraints, hidden dependencies
- Propose alternatives, explain trade-offs
- Agree on approach before coding

### Implement (dev-loop)
1. Create `.devloop/` with `context.md`, `state.json`, `tasks.json`
2. One task at a time — implement, test, advance state
3. Delete `.devloop/` when all tasks done

### Validate
- Run `python -m pytest tests/ -q` — all tests must pass
- Run 15-date forward batch: `Rank(ret × vol_ratio) + Rank(sector_rel_ret) − Rank(vol)` baseline is **59% win, +0.73% avg 10d return**
- Compare every change against this baseline
- Hypothesis rejected if performance degrades

### Commit
- `git add -A && git commit -m "description"`
- Use descriptive first line. Include before/after metrics in body.

## Testing Conventions
- `tests/test_factors.py` — 12 tests for factor signal generation
- Test data: `make_data(n_stocks, n_dates, with_volume)` factory
- Always test: empty input, missing symbols, insufficient history, formula correctness
- Formula tests replicate the rank math to verify conviction values

## Key Files
- `src/factors.py` — `generate_factor_signals(data, date, sector_map=None)`, `get_factor_names()`
- `src/db.py` — `load_symbol_data(universe)`, `get_sector_map(universe)`
- `forward_check.py` — `--date YYYY-MM-DD --strategy factor --top 5`
- `daily_scan.py` — production pipeline
