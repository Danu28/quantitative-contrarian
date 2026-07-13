# Project Context

## Requirement
Simplify dashboard to show ONLY Factor Model report. Deploy to GitHub Pages at https://danu28.github.io/quantitative-contrarian/

## Deployment Structure
- GitHub Pages site serves content from `reports/` directory
- index.html (from docs/index.html) is at site root
- factor-scan-{date}.json is in same directory as index.html
- Fetch path: relative `factor-scan-{date}.json` (no leading slash)

## What to Remove
- Contrarian strategy card + JS render function
- Momentum strategy card + JS render function
- Backtest summary table
- Regime reference table
- Strategy count KPI detail

## What to Keep
- Header (simplified)
- KPI grid (universe, report count, regime)
- Factor Model card with top 10 picks + scan date
- Theme toggle
- File-protocol warning

## Fetch Strategy
- Single relative path: `factor-scan-{date}.json`
- Date range: -5 to +44 days from browser's clock
- No fallback paths needed (same directory on GitHub Pages)

## Local Testing
Serve from reports/ directory:
  python -m http.server 8080 -d reports/
Then open: http://localhost:8080/index.html
