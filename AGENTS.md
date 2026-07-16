# Project Workflow

## Global Defaults
- **Ponytail mode** is always active — write minimal code, no over-engineering, delete before adding
- **Surgical changes** — every edit should be as small as possible. One intent per change. No bulk rewrites.
- **Auto-commit** — commit at logical stops (hypothesis accepted, bug fixed, dev-loop completed). Clean, descriptive, one intent per commit.
- **No autopush** — never push without explicit user approval
- **Branch convention**: all work on `feature/*` branches, named after the change

## Behavioral Rules

### 1. Think Before Coding
State assumptions explicitly. If multiple interpretations exist, present them — don't pick silently. If something is unclear, stop and ask. Don't hide confusion.

### 2. Simplicity First
Minimum code that solves the problem. No speculative features, no abstractions for single-use code, no "flexibility" that wasn't requested. If you write 200 lines and it could be 50, rewrite it.

### 3. Surgical Changes
Touch only what you must. Don't "improve" adjacent code, comments, or formatting. Don't refactor things that aren't broken. Match existing style. Clean up only imports/variables that YOUR changes made unused — don't delete pre-existing dead code unless asked. The test: every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution
Define success criteria before implementing. For multi-step tasks, state a brief plan with verification checkpoints. Loop until verified — don't claim completion without evidence.

## Skill Order (in this sequence — must follow strictly)

1. **alpha-factor-discovery** — generate hypotheses with economic mechanisms, formulas, falsification tests
2. **quant-research** — validate hypotheses with quantitative research, statistics, investigation scripts
3. **first-principles** — question assumptions, plan approach, agree on trade-offs before coding
4. **dev-loop** — implement changes one task at a time with state tracking in `.devloop/`
5. **beautiful-reports** — generate HTML reports (when output visualization is needed)

After dev-loop tasks complete, delete `.devloop/` directory.

## Workflow for Factor Model Changes

### 1. Discover (alpha-factor-discovery)
- Generate hypotheses: economic intuition → mathematical formula → expected IC → falsification plan
- Produce ranked catalog with prior probabilities and validation priorities
- Every hypothesis is assumed FALSE until proven otherwise

### 2. Research (quant-research)
- Build standalone investigation scripts (`_investigate_*.py`) — never modify production code at this stage
- Test the proposed signal against multi-period dataset (2-year, 6 quarters)
- Compare signal vs baseline on aggregate and per-period returns
- Compute correlations, decile analysis, win rates
- Only proceed to planning if investigation shows consistent edge

### 3. Plan (first-principles)
- Question assumptions, constraints, hidden dependencies
- Propose alternatives, explain trade-offs
- Agree on approach before any code changes

### 4. Implement (dev-loop)
1. Create `.devloop/` with `context.md`, `state.json`, `tasks.json`
2. One task at a time — implement, test, advance state
3. Delete `.devloop/` when all tasks done

### 5. Validate
- Run `python -m pytest tests/ -q` — all tests must pass
- Run 15-date forward batch via `python batch_fwd_15.py`
- Run 1-year validation via `python batch_fwd_1yr.py` for accepted hypotheses
- Compare against current best: **~75% win, ~+2.0% avg 10d return**
- If performance degrades → reject hypothesis, revert to previous state, document why

### Hypothesis Lifecycle
1. Generate via **alpha-factor-discovery** — structured analysis with economic mechanism
2. Validate via **quant-research** — investigation scripts, multi-period data, statistical tests
3. Plan via **first-principles** — question, simplify, agree on approach
4. Implement via **dev-loop** — tracked, one-task-at-a-time changes
5. Validate via forward batch against baseline (pytest + batch_fwd_15 + batch_fwd_1yr)
6. **Accept** if performance holds or improves → commit with before/after metrics
7. **Reject** if performance degrades → `git checkout -- src/factors.py` and revert test changes
8. Move to next hypothesis

### Commit
- `git add -A && git commit -m "description"`
- Use descriptive first line. Include before/after metrics in body.

## Testing Conventions
- `tests/test_factors.py` — 10 tests for factor signal generation
- Test data: `make_data(n_stocks, n_dates, with_volume)` factory
- Always test: empty input, missing symbols, insufficient history, formula correctness
- Formula tests replicate the rank math to verify conviction values
- After any factors.py change, run full test suite before validating

## Key Files
- `src/factors.py` — `generate_factor_signals(data, date, sector_map=None)`, `get_factor_names()`, `diversify_factor_signals()`
- `src/db.py` — `load_symbol_data(universe)`, `get_sector_map(universe)`
- `forward_check.py` — `--date YYYY-MM-DD --strategy factor --top 5 --universe nifty50`
- `batch_fwd_15.py` — 15-date quick validation (`--universe nifty50`)
- `batch_fwd_1yr.py` — 1-year non-overlapping validation (`--universe nifty50 --year-offset 0`)
- `daily_scan.py` — production pipeline
- `compare_strategies.py` — side-by-side factor vs contrarian comparison
