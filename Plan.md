# Reverse Engineering Future Winners — Research Plan

## Step 1 — Question Everything

### Actual Problem

Reverse engineer the measurable characteristics of NIFTY 50 (→NIFTY 500) stocks that become the biggest winners over 1–4 week horizons, using only data available **before** the move begins. Every discovered characteristic must survive statistical testing and out-of-sample validation.

This is a **discovery** problem, not a pipeline-building problem. The question is not "how do we build a system?" but **"what do winning stocks look like before they win?"**

### Assumptions Discovered

| # | Assumption | Status |
|---|-----------|--------|
| 1 | NIFTY 50 stocks exhibit measurable pre-move characteristics that repeat over time | Unknown — must be tested; semi-strong EMH predicts no such patterns exist |
| 2 | A 1–4 week pre-move window is the right lookback period to find signals | Unknown — the window itself must be discovered, not assumed |
| 3 | Free data (Yahoo Finance) is sufficient to capture the characteristics | Questionable — institutional data may contain information free data misses |
| 4 | The "biggest winners" can be objectively defined | Required — needs a clear, testable definition before research begins |
| 5 | Reverse engineering (start from winners, work backward) is superior to forward feature scanning | Reasonable — aligns with the prompt's stated methodology; focuses the search space |
| 6 | Winner characteristics generalize across different market regimes | Unknown — must be tested; regimes may have different winner profiles |
| 7 | 50 stocks provide enough winner instances for statistical significance | Questionable — 50 stocks × 3 years × 4-week windows = limited winner sample |
| 8 | Price and volume data alone can distinguish future winners | Unknown — sector, corporate actions, or macro factors may be required |
| 9 | An institutional quant research process can be executed without paid data | Questionable — some characteristics (like fundamental ratios) are unavailable for free |
| 10 | "Everything must be proven" is operationally achievable | Aspirational — requires a defined stopping criterion for "enough evidence" |

### Invalid Assumptions (Rejected)

| Assumption | Why Invalid |
|------------|-------------|
| A production pipeline should be built first | Premature — no signal has been discovered yet; building before discovering wastes time |
| Traditional indicators (RSI, MACD, ADX) are useful | No evidence they work; including them biases the search toward known (and likely arbitraged) signals |
| ML/DL models should be prepared in advance | The model should follow the discovery, not precede it |
| The research output must be a live trading system | The immediate output is a set of discovered characteristics; a trading system is a separate follow-on |
| Pre-defining a feature list is necessary | Pre-defining features biases discovery; the search should be as open as possible given data constraints |

### Missing Information

| Item | Impact | Resolution |
|------|--------|------------|
| Exact definition of "biggest winner" | Critical — changes the entire analysis | Must be defined before research begins (proposals below) |
| Pre-move window length | Critical — changes what characteristics are examined | Must be tested parametrically (1–4 weeks) |
| Minimum winner magnitude | High — determines how many instances exist | Set based on distribution of historical returns |
| Data history length | High — more history = more winner instances | Minimum 5 years; ideally 10+ |
| Universe beyond NIFTY 50 | Medium — affects statistical power | NIFTY 50 first; expand to 500 if needed |
| Acceptable false positive rate | Medium — determines statistical rigor | Standard: p < 0.05 with Bonferroni correction for multiple tests |

---

## Step 2 — Remove Everything Possible

### Candidates for Removal

| Item | Reason | Impact | Risk |
|------|--------|--------|------|
| Production pipeline code (signal.py, dashboard/, report.py) | No signal exists yet to pipeline; pure discovery needs no infrastructure | Reduces scope by ~50%; focuses effort on actual research | Low — can build after discovery |
| Pre-defined feature list (MA slopes, ATR%, RSI, etc.) | Biases the search toward known indicators; contradicts "never assume any indicator works" | Opens the search to unexpected characteristics | Low — add features as hypotheses, not defaults |
| ML/DL model code | No discovery has happened yet; no basis for model selection | Eliminates premature engineering | Low — models follow discovery |
| Database, API, orchestration | No pipeline needed; raw data + analysis scripts suffice | Zero infrastructure | Low |
| Walk-forward backtesting engine | Not applicable to discovery phase; used later to validate a strategy | Simplifies to basic statistical tests | Low — add when testing tradability |
| Web dashboard | Premature delivery mechanism before discovery | Removes UI distraction | Low |
| Benchmark-relative returns (as default target) | Prompt says "biggest winners" — absolute top performers, not benchmark-beaters | Changes the target variable | Medium — requires careful winner definition |

### Expected Net Reduction

~60% removed vs a typical quant pipeline approach. What remains is a pure research process with minimal infrastructure.

---

## Step 3 — Simplify

### Research Architecture

The system reduces to a single research loop:

```
Data → Identify Winners → Extract Pre-Move State → Compare → Validate → Report Characteristics
```

### Simplified Research Workflow

Instead of building a pipeline:

```
1. Define "biggest winner" objectively (return threshold, horizon, ranking)
2. Scan NIFTY 50 history → tag all winner and non-winner instances
3. For each instance, collect the pre-move window data
4. For each candidate characteristic:
   a. Compute it for all instances at the pre-move point
   b. Compare distribution: winners vs non-winners
   c. Test for statistical significance (t-test, Mann-Whitney, effect size)
5. Multiple testing correction: only keep findings that survive
6. Validate surviving characteristics:
   a. Out-of-sample (later time period)
   b. Across market regimes
   c. Sensitivity to winner definition parameters
7. Report: "Winners before winning have characteristic X with p < Y and effect size Z"
```

### Winner Definition (Proposed)

To be validated, not assumed:

| Parameter | Default Value | Test Alternatives |
|-----------|---------------|-------------------|
| Return horizon | 4 weeks (20 trading days) | 1 week, 2 weeks, 3 weeks |
| Winner threshold | Top 10% of universe by absolute return | Top 20%, top 5%, >10% gain, >15% gain |
| Reference universe | NIFTY 50 index constituents | Same, lagged by 1 day |
| Minimum instances | 30 winner events | Fewer may produce unreliable statistics |

### Candidate Characteristics (Hypotheses, Not Assumptions)

These are starting hypotheses to test, not a fixed feature list. Each must stand or fall on evidence.

**Price structure:**
- Distance from N-day high/low (lookback: 10, 20, 50 days)
- Price vs moving average (10, 20, 50 days)
- Slope of moving averages
- Recent return decile within universe (1, 2, 4 weeks)

**Volume structure:**
- Volume vs its own N-day average (10, 20 days)
- Volume vs universe average volume
- Volume trend (slope over 5, 10 days)
- Volume × price (raw dollar volume)

**Volatility structure:**
- Rolling standard deviation of daily returns (10, 20 days)
- Average true range as % of price
- Volatility rank within universe
- Volatility regime (expanding vs contracting)

**Cross-sectional:**
- Price rank within universe
- Volatility rank within universe
- Volume rank within universe
- Sector concentration of recent winners/losers

**Structure of returns:**
- Skewness of recent returns
- Serial correlation of daily returns
- Gap frequency and magnitude
- Number of up days vs down days

**Note:** This list is open. Any characteristic found during the research that shows separation between winners and non-winners is valid.

### What Remains Complex

- Avoiding survivorship bias in historical winner identification — index constituents change
- Defining the pre-move window without lookahead — the "start" of a move is ambiguous
- Multiple testing correction with limited data — 50 stocks × N features creates false positive risk
- Distinguishing between characteristics that cause vs correlate with winning

### Module Structure (Minimal)

```
reverse_engineer/
├── data.py           # Fetch OHLCV for current + historical NIFTY 50 constituents
├── winners.py        # Identify winner instances based on objective criteria
├── characteristics.py # Compute candidate pre-move characteristics
├── compare.py        # Statistical comparison: winners vs non-winners
├── validate.py       # Out-of-sample and regime stability testing
└── report.py         # Produce ranked table of discovered characteristics
```

No signal.py. No dashboard/. No models/. No ML code. Pure research tools.

---

## Step 4 — Accelerate

### First Iteration Targets

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Universe | NIFTY 50 | Fastest to analyze; expand if signal found |
| Data history | 10 years | Maximizes winner instances for statistical power |
| Winner definition | Top 10% by absolute return over 4 weeks | Clear, testable, replicable |
| Pre-move window | 4 weeks before the move | Matches the return horizon; test alternatives later |
| Characteristics | 10–15 hypotheses (from candidate list) | Enough for meaningful discovery; small enough for correction |
| Statistical test | Mann-Whitney U (non-parametric) | No distribution assumptions; robust to outliers |
| Significance threshold | p < 0.05 after Bonferroni correction | Stringent; reduces false positives |

### Expected Timeline

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Define winners + data collection | 1 day | Historical instances of biggest winners |
| Characteristic computation | 1–2 days | Pre-move snapshot for all instances |
| Statistical comparison | 1 day | Ranked table: which characteristics separate winners from non-winners |
| Out-of-sample validation | 1 day | Confirmed characteristics hold in unseen periods |
| Report | 1 day | Documented discovered characteristics with evidence |

**First discovery result in 4–6 days.**

### Validation Strategy

1. **In-sample discovery:** Split data 70/30 chronological (older 70% for discovery, recent 30% for validation)
2. **Statistical gate:** Only characteristics with p < 0.05 (corrected) and effect size > 0.3 (Cohen's d) proceed
3. **Out-of-sample check:** Do the discovered characteristics also separate winners in the validation period?
4. **Regime stability:** Do characteristics hold in bull, bear, and sideways markets?
5. **Parameter sensitivity:** Do results hold if winner threshold changes (10% → 15% → 20%)?
6. **Permutation test:** Shuffle winner labels N times; do real characteristics beat random?

### Success Criteria

| Metric | Target | Meaning |
|--------|--------|---------|
| Significant characteristics | ≥ 1 with p < 0.05 (corrected) | At least one measurable difference exists |
| Effect size (Cohen's d) | > 0.3 | Difference is practically meaningful, not just statistically significant |
| OOS replication | Characteristic survives in validation period | Not a spurious in-sample artifact |
| Regime consistency | Does not flip sign across regimes | Robust, not period-specific |
| Permutation p-value | < 0.05 | Beats random labeling |
| Sensitivity | Stable across ±20% of winner threshold | Not an artifact of threshold choice |

If zero characteristics survive all gates, the honest answer is: **no discoverable pre-move pattern exists in NIFTY 50 using free data over this horizon.**

---

## Step 5 — Automate

### Not Yet — Discovery Must Complete First

| Candidate | When | ROI |
|-----------|------|-----|
| Data refresh automation | After discovery is validated and characteristics are known | High — enables testing on new data |
| Characteristic computation script | After at least 3 characteristics pass validation | High — repeatable measurement |
| Automated retesting | After 6 months of new data | High — detects characteristic decay |
| Pipeline to trading system | Only if discovered characteristics predict future winners in forward testing | High — but premature until then |

Do not automate anything until at least one characteristic survives the full validation chain.

---

# Final Deliverable

## Executive Summary

Reverse engineer what makes NIFTY 50 stocks become biggest winners before the move begins. Start with an objective definition of "biggest winner," scan 10 years of history to collect all winner instances, extract their pre-move state across 10–15 candidate characteristics, and statistically compare them against non-winners. Apply multiple testing correction, out-of-sample validation, regime stability checks, and permutation tests. Every conclusion must survive the full evidence chain. If no characteristic survives, report that honestly. First discovery results expected in 4–6 days. Only after validated characteristics are identified should any pipeline or trading system be considered.

## Root Cause

The original framing conflated two separate problems: (1) discovering what makes stocks winners, and (2) building a system to predict them. The discovery must come first — you cannot build a predictive system before you know what to predict, let alone what predicts it. The prompt's "reverse engineering" approach corrects this by starting from known winners and working backward, rather than starting from features and testing forward.

## Key Assumptions

- NIFTY 50 is large enough to generate statistically meaningful winner instances over 10 years
- Yahoo Finance data quality is sufficient for characteristic discovery
- Winners can be objectively defined (top X% by absolute return over Y weeks)
- A pre-move window of comparable length to the return horizon is appropriate
- Non-parametric statistics (Mann-Whitney U) are appropriate for comparing winner vs non-winner distributions
- Multiple testing correction (Bonferroni) is necessary given the number of candidate characteristics
- Characteristics found in-sample should replicate out-of-sample
- If no characteristic survives validation, the honest answer is "no pattern found"

## Items Removed (vs typical quant approach)

| Removed | Rationale |
|---------|-----------|
| Production pipeline (signal.py, dashboard/) | Premature — no discovered signal to deliver |
| Pre-defined indicator features (RSI, MACD, ATR%, MA slopes as defaults) | Biases the search; contradicts "never assume any indicator works" |
| ML/DL models | Models follow discovery, not precede it |
| Walk-forward backtesting engine | Not applicable to discovery phase |
| Database / infrastructure | Raw data + analysis scripts are sufficient |
| Benchmark-relative target | Prompt says "biggest winners" — absolute, not relative |
| Sequential 10-phase process | Replaced with a single discovery loop: identify → extract → compare → validate |
| Strategy design (entry/exit/position sizing) | Premature — no discovered characteristic to trade on yet |

## Simplified Solution

A single Python package with five scripts:

```
reverse_engineer/
├── data.py           # Fetch OHLCV for current + historical NIFTY 50 constituents
├── winners.py        # Identify winner instances based on objective criteria
├── characteristics.py # Compute candidate pre-move characteristics
├── compare.py        # Statistical comparison: winners vs non-winners
└── validate.py       # Out-of-sample and regime stability testing
```

No database. No API keys. No ML. No dashboard. No indicators assumed. No pipeline. One analysis to answer: **do future winners look different before they win?**

## Trade-offs

| Choice | Pro | Con |
|--------|-----|-----|
| Reverse engineering (start from winners) | Focuses search; avoids testing infinite features | May miss characteristics that predict but don't precede extreme winners |
| Absolute returns (not benchmark-relative) | Aligns with "biggest winners" prompt | Noisier target; includes market beta |
| 10 years of data | More winner instances; better statistics | Survivorship bias risk with old data |
| Non-parametric tests | No distribution assumptions | Less statistical power than parametric if assumptions hold |
| Bonferroni correction | Strong false positive control | May miss real but subtle characteristics |
| Pure research (no pipeline) | No infrastructure burden; faster iteration | No production signal output from Phase 1 |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| No characteristic survives validation | Medium — market efficiency | This is a valid outcome; report it honestly |
| Survivorship bias in 10-year history | Medium — NIFTY 50 constituents change | Track reconstitution history; include delisted stocks |
| Winner definition arbitrariness | High — different thresholds yield different winners | Test sensitivity across multiple definitions |
| Multiple testing reduces power | High — many characteristics × few winner instances | Consider FDR (Benjamini-Hochberg) as alternative to Bonferroni |
| Pre-move window ambiguous | Medium — move "start" is not clearly defined | Test multiple window definitions; report sensitivity |
| Characteristics decay after publication | High — any discovered pattern may be arbitraged | Document the finding; monitor over time |
| Free data misses key characteristics | Medium — some signals require fundamental or alternative data | Note limitation in report; candidate for future paid data |

## Recommended Next Steps

1. **Define winner criteria** — Settle on return horizon (4 weeks), universe (NIFTY 50), and winner threshold (top 10% by absolute return). Document the definition.
2. **Build data collector** (`data.py`) — Fetch 10 years of daily OHLCV for current AND historical NIFTY 50 constituents. Include the index for context.
3. **Build winner identifier** (`winners.py`) — Scan rolling 4-week windows; tag each stock-period as "winner" if it ranks in top 10% of absolute returns. Collect the pre-move window for each instance.
4. **Build characteristic analyzer** (`characteristics.py` + `compare.py`) — For each candidate characteristic, compute the pre-move value for all instances. Statistically compare winners vs non-winners.
5. **Full discovery run** — Execute the loop. Apply validation gates. Produce the ranked characteristic table.
6. **Decision gate** — If ≥ 1 characteristic survives all validation → proceed to deeper analysis and eventually pipeline construction. If zero survive → report no pattern found; consider expanding universe to NIFTY 500 or testing different horizons.

Start with Step 1. It requires zero code and determines everything downstream.
