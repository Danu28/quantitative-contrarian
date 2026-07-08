# Project Context

## Requirement
Set up automated daily run of `daily_scan.py` at 9:00 AM IST, deploying the HTML report to GitHub Pages for live URL access (no download needed).

## Goals
- Run daily scan automatically every morning before market open
- Deploy HTML report to GitHub Pages → live, bookmarkable URL
- Keep historical reports organized by date
- Minimal maintenance, low cost
- Reliable execution

## Tech Stack
- Python 3.10+ (pandas, numpy, yfinance, scipy)
- GitHub Actions (cron schedule + Pages deployment)
- GitHub Pages (static hosting for HTML reports)
- peaceiris/actions-gh-pages for branch deployment

## Design Decisions
- GitHub Actions cron at 3:30 UTC (9:00 AM IST, UTC+5:30, no DST)
- Deploy to `gh-pages` branch using peaceiris/actions-gh-pages
- Generate two files: `latest.html` (overwritten daily, bookmarkable) and `daily-scan-YYYY-MM-DD.html` (historical)
- Sequential fetching of 48 stocks takes ~2-5 min, well within free tier limits

## Risks / Edge Cases
- GitHub Actions free tier: 2000 min/month, ~3 min/run = ~90 min/month = well within free tier
- Market holidays: scan returns no signals gracefully
- yfinance rate limits: handled by sequential fetching + 0.5s delay in fetch_universe
- Cron is best-effort on GitHub; occasional delays of minutes are acceptable
- First run needs to fetch all historical data (~10 min); subsequent runs fetch ~5 rows each (~2 min)
- GitHub Pages deployment requires Pages to be enabled in repo Settings → Pages → Source: "Deploy from a branch", branch: gh-pages, folder: / (root)
