from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest import generate_signals, find_trading_dates, build_horizon_results
from src.db import load_symbol_data
from src.features import precompute_all_characteristics
from src.reporting import TEMPLATE_CSS, _classify_regime


def build_portfolio(signals, horizon_data, horizon, regime, capital):
    max_pos = regime["max_positions"]
    top = signals.head(max_pos)
    trades = []
    for _, row in top.iterrows():
        sym = row["symbol"]
        hd = horizon_data.get(horizon, {})
        for r in hd.get("results", []):
            if r["symbol"] == sym and r["status"] == "ok":
                alloc = capital / max_pos
                pnl = alloc * r["return_pct"] / 100
                trades.append({
                    "symbol": sym,
                    "entry_date": r["entry_date"],
                    "exit_date": r["exit_date"],
                    "entry_price": r["entry_price"],
                    "exit_price": r["exit_price"],
                    "return_pct": r["return_pct"],
                    "pnl": pnl,
                    "regime": regime["trend_label"],
                    "regime_20d": regime["trend_20d"],
                })
                break
    return trades





def _bar(val, max_val, color="var(--accent-1)"):
    pct = abs(val) / abs(max_val) * 100 if max_val != 0 else 0
    return f'<div class="bar"><div class="bar-fill" style="width:{pct:.0f}%;background:{color}"></div></div>'


def generate_html(
    universe_slug, years, horizon, capital, sample_interval,
    all_dates, sample_dates, dates_with_signals, dates_no_signals, signal_counts,
    df, wins, losses, trade_returns, hit_rate, pl_ratio, up_avg, dn_avg,
    win_loss_ratio, conf_95_lo, conf_95_hi, max_cons_win, max_cons_loss,
    first_wr, later_wr, g1, g2, g3, g4, g5,
):
    gates_pass = sum([g1, g2, g3, g4, g5])
    recommendation = "Ready for Paper Trading" if gates_pass >= 4 else "More Research Needed"
    rec_color = "var(--accent-1)" if gates_pass >= 4 else "var(--accent-3)"

    regime_rows = ""
    for regime_label in ["Strong Bull", "Bull", "Sideways", "Bear", "Crash"]:
        sub = df[df["regime"] == regime_label]
        if sub.empty:
            continue
        w = sub[sub["return_pct"] > 0]
        l_ = sub[sub["return_pct"] <= 0]
        wr = len(w) / len(sub) * 100
        pf = w["return_pct"].sum() / abs(l_["return_pct"].sum()) if len(l_) else float("inf")
        pf_s = "INF" if pf == float("inf") else f"{pf:.2f}"
        avg = sub["return_pct"].mean()
        best = sub["return_pct"].max()
        worst = sub["return_pct"].min()
        max_val = max(abs(best), abs(worst))
        regime_rows += f"""
        <tr>
            <td><span class="regime-dot r-{regime_label.lower().replace(' ', '-')}"></span>{regime_label}</td>
            <td class="num">{len(sub)}</td>
            <td class="num">{wr:.1f}%</td>
            <td class="num {"pos" if avg > 0 else "neg"}">{avg:+.2f}%</td>
            <td class="num pos">{best:+.2f}%</td>
            <td class="num neg">{worst:+.2f}%</td>
            <td class="num">{pf_s}</td>
        </tr>"""

    # Build distribution buckets
    buckets = [-20, -10, -5, -2, 0, 2, 5, 10, 20]
    dist_rows = ""
    for i in range(len(buckets) - 1):
        lo, hi = buckets[i], buckets[i + 1]
        count = ((trade_returns >= lo) & (trade_returns < hi)).sum()
        pct = count / len(trade_returns) * 100
        label = f"{lo:+.0f}% to {hi:+.0f}%" if lo >= 0 else f"{lo:.0f}% to {hi:+.0f}%"
        bar_color = "var(--accent-1)" if lo >= 0 else "var(--red)"
        dist_rows += f"""
        <tr>
            <td>{label}</td>
            <td class="num">{count}</td>
            <td class="num">{pct:.1f}%</td>
            <td>{_bar(pct, 100, bar_color)}</td>
        </tr>"""

    # Last bucket for >20 or <-20
    over = (trade_returns >= 20).sum()
    under = (trade_returns < -20).sum()
    if over:
        pct = over / len(trade_returns) * 100
        dist_rows += f"""
        <tr>
            <td>&ge; +20%</td>
            <td class="num">{over}</td>
            <td class="num">{pct:.1f}%</td>
            <td>{_bar(pct, 100, 'var(--accent-1)')}</td>
        </tr>"""
    if under:
        pct = under / len(trade_returns) * 100
        dist_rows += f"""
        <tr>
            <td>&lt; -20%</td>
            <td class="num">{under}</td>
            <td class="num">{pct:.1f}%</td>
            <td>{_bar(pct, 100, 'var(--red)')}</td>
        </tr>"""

    universe_name = universe_slug.upper()

    html = f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Forward Validation — {universe_name}</title>
<style>{TEMPLATE_CSS}</style>
<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 24px; box-shadow: var(--shadow); }
  .card h2 { font-family: 'Playfair Display', serif; font-size: 1.1rem; font-weight: 600; margin-bottom: 12px; color: var(--muted); }
  .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }
  @media (max-width: 700px) { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }
  @media (max-width: 400px) { .kpi-grid { grid-template-columns: 1fr; } }
  .kpi { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; text-align: center; box-shadow: var(--shadow); }
  .kpi .value { font-family: 'JetBrains Mono', monospace; font-size: 1.8rem; font-weight: 500; }
  .kpi .label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; color: var(--muted); margin-top: 4px; }
  .pos { color: var(--positive); }
  .neg { color: var(--negative); }
  .table-wrap { overflow-x: auto; }
  th.num, td.num { font-family: 'JetBrains Mono', monospace; text-align: right; }
  .bar { width: 100%; height: 8px; background: var(--border); border-radius: 4px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 4px; transition: width 0.6s ease; }
  .regime-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; }
  .r-crash { background: #DC2626; }
  .r-bear { background: #F97316; }
  .r-sideways { background: var(--amber); }
  .r-bull { background: var(--positive); }
  .r-strong-bull { background: #059669; }
  .verdict-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 24px; box-shadow: var(--shadow); margin-top: 24px; }
  .verdict-card h2 { font-family: 'Playfair Display', serif; margin-bottom: 16px; }
  .gate-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--border); }
  .gate-row:last-child { border-bottom: none; }
  .gate-status { font-family: 'JetBrains Mono', monospace; font-weight: 500; padding: 2px 10px; border-radius: 4px; font-size: 0.85rem; }
  .gate-pass { color: var(--positive); background: rgba(46,111,64,0.1); }
  .gate-fail { color: var(--negative); background: rgba(220,38,38,0.1); }
  .section { margin-bottom: 32px; }
  .section-title { font-family: 'Playfair Display', serif; font-size: 1.3rem; font-weight: 600; margin-bottom: 16px; padding: 0 24px 8px 24px; border-bottom: 2px solid var(--positive); }
  .table-wrap { overflow-x: auto; }
  .recommendation {{ text-align: center; padding: 20px; margin-top: 24px; border-radius: 12px; font-size: 1.2rem; font-weight: 600; background: {rec_color}; color: #fff; }}
  @media print {{ body {{ padding: 0; background: #fff; }} .card, .kpi, .verdict-card {{ box-shadow: none; break-inside: avoid; }} .theme-toggle {{ display: none; }} }}
</style>
</head>
<body>
<div class="container">

<button class="theme-toggle" onclick="document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark'">Toggle Theme</button>

<header>
  <div>
    <h1>Forward Validation &mdash; {universe_name}</h1>
    <div class="sub">Walk-forward accuracy assessment over {years} years</div>
  </div>
  <div class="meta">
    <div>Horizon: {horizon} trading days</div>
    <div>Capital: INR {capital:,.0f}</div>
    <div>Sampling: every {sample_interval} trading days</div>
  </div>
</header>

<div class="kpi-grid">
  <div class="kpi">
    <div class="value">{len(sample_dates)}</div>
    <div class="label">Sample Dates</div>
  </div>
  <div class="kpi">
    <div class="value">{len(df)}</div>
    <div class="label">Total Trades</div>
  </div>
  <div class="kpi">
    <div class="value" style="color:{'var(--accent-1)' if hit_rate>50 else 'var(--red)'}">{hit_rate:.1f}%</div>
    <div class="label">Win Rate</div>
  </div>
  <div class="kpi">
    <div class="value" style="color:{'var(--accent-1)' if trade_returns.mean()>0 else 'var(--red)'}">{trade_returns.mean():+.2f}%</div>
    <div class="label">Avg Return</div>
  </div>
  <div class="kpi">
    <div class="value">{pl_ratio:.2f}</div>
    <div class="label">Profit Factor</div>
  </div>
  <div class="kpi">
    <div class="value" style="color:var(--accent-1)">{dates_with_signals/len(sample_dates)*100:.0f}%</div>
    <div class="label">Signal Coverage</div>
  </div>
  <div class="kpi">
    <div class="value">{max_cons_win}</div>
    <div class="label">Max Cons Wins</div>
  </div>
  <div class="kpi">
    <div class="value">{max_cons_loss}</div>
    <div class="label">Max Cons Losses</div>
  </div>
</div>

<div class="section">
  <h2 class="section-title">Return Distribution</h2>
  <div class="card">
    <div class="table-wrap">
    <table>
      <thead><tr><th>Range</th><th class="num">Count</th><th class="num">%</th><th>Distribution</th></tr></thead>
      <tbody>{dist_rows}</tbody>
    </table>
    </div>
  </div>
</div>

<div class="section">
  <h2 class="section-title">Accuracy by Market Regime</h2>
  <div class="card">
    <div class="table-wrap">
    <table>
      <thead><tr><th>Regime</th><th class="num">Trades</th><th class="num">Win%</th><th class="num">Avg Return</th><th class="num">Best</th><th class="num">Worst</th><th class="num">P.Factor</th></tr></thead>
      <tbody>{regime_rows}</tbody>
    </table>
    </div>
  </div>
</div>

<div class="section">
  <h2 class="section-title">Trade Statistics</h2>
  <div class="card">
    <div class="table-wrap">
    <table>
      <thead><tr><th>Metric</th><th class="num">Value</th></tr></thead>
      <tbody>
        <tr><td>Win Rate</td><td class="num {"pos" if hit_rate>40 else "neg"}">{hit_rate:.1f}%</td></tr>
        <tr><td>Total Wins / Losses</td><td class="num">{len(wins)} / {len(losses)}</td></tr>
        <tr><td>Avg Win</td><td class="num pos">{wins['return_pct'].mean():+.2f}%</td></tr>
        <tr><td>Avg Loss</td><td class="num neg">{losses['return_pct'].mean():+.2f}%</td></tr>
        <tr><td>Avg Return (Expectancy)</td><td class="num {"pos" if trade_returns.mean()>0 else "neg"}">{trade_returns.mean():+.2f}%</td></tr>
        <tr><td>Median Return</td><td class="num">{trade_returns.median():+.2f}%</td></tr>
        <tr><td>Std Dev</td><td class="num">{trade_returns.std():.2f}%</td></tr>
        <tr><td>Best Trade</td><td class="num pos">{trade_returns.max():+.2f}%</td></tr>
        <tr><td>Worst Trade</td><td class="num neg">{trade_returns.min():+.2f}%</td></tr>
        <tr><td>Profit Factor</td><td class="num">{pl_ratio:.2f}</td></tr>
        <tr><td>Win/Loss Magnitude Ratio</td><td class="num">{win_loss_ratio:.2f}</td></tr>
        <tr><td>95% CI of Mean</td><td class="num">[{conf_95_lo:+.2f}%, {conf_95_hi:+.2f}%]</td></tr>
        <tr><td>Skewness</td><td class="num">{trade_returns.skew():.2f}</td></tr>
        <tr><td>Kurtosis</td><td class="num">{trade_returns.kurtosis():.2f}</td></tr>
        <tr><td>Max Consecutive Wins</td><td class="num">{max_cons_win}</td></tr>
        <tr><td>Max Consecutive Losses</td><td class="num">{max_cons_loss}</td></tr>
        <tr><td>Rank-1 Signal Win Rate</td><td class="num">{first_wr:.1f}%</td></tr>
        <tr><td>Rank-2+ Signal Win Rate</td><td class="num">{later_wr:.1f}%</td></tr>
      </tbody>
    </table>
    </div>
  </div>
</div>

<div class="section">
  <h2 class="section-title">Validation Gates</h2>
  <div class="verdict-card">
    <div class="gate-row">
      <span>Gate 1: Win rate &gt; 40%</span>
      <span class="gate-status {'gate-pass' if g1 else 'gate-fail'}">{hit_rate:.1f}%</span>
    </div>
    <div class="gate-row">
      <span>Gate 2: Positive expectancy</span>
      <span class="gate-status {'gate-pass' if g2 else 'gate-fail'}">{trade_returns.mean():+.2f}%</span>
    </div>
    <div class="gate-row">
      <span>Gate 3: Profit factor &gt; 1.5</span>
      <span class="gate-status {'gate-pass' if g3 else 'gate-fail'}">{pl_ratio:.2f}</span>
    </div>
    <div class="gate-row">
      <span>Gate 4: At least 100 trades</span>
      <span class="gate-status {'gate-pass' if g4 else 'gate-fail'}">{len(df)}</span>
    </div>
    <div class="gate-row">
      <span>Gate 5: Avg win &gt; |avg loss|</span>
      <span class="gate-status {'gate-pass' if g5 else 'gate-fail'}">{up_avg:+.2f}% vs {dn_avg:+.2f}%</span>
    </div>
  </div>
  <div class="recommendation">
    {gates_pass}/{5} Gates Passed &mdash; {recommendation}
  </div>
</div>

</div>
</body>
</html>"""
    return html


def validate(universe_slug: str, years: int = 3, horizon: int = 21, capital: float = 10_000_000, sample_interval: int = 5, output: str | None = None):
    print(f"{'='*70}")
    print(f"  WALK-FORWARD VALIDATION")
    print(f"  Universe: {universe_slug}")
    print(f"  Period:   last {years} years")
    print(f"  Horizon:  {horizon} trading days")
    print(f"  Capital:  INR {capital:,.0f}")
    print(f"  Sampling: every {sample_interval} trading days")
    print(f"{'='*70}")

    print(f"\n  Loading data...")
    data = load_symbol_data(universe_slug, years=years)
    print(f"  Loaded {len(data)} stocks")

    print(f"  Pre-computing characteristics...")
    char_data = precompute_all_characteristics(data, window=horizon)
    all_dates = sorted(set(d for s in char_data for d in char_data[s].index))
    print(f"  Trading dates: {len(all_dates)}")

    sample_dates = all_dates[sample_interval:-horizon:sample_interval]
    print(f"  Sample dates:  {len(sample_dates)}")

    all_trades: list[dict] = []
    dates_with_signals = 0
    dates_no_signals = 0
    signal_counts: list[int] = []

    for i, entry_date in enumerate(sample_dates):
        if (i + 1) % 20 == 0:
            print(f"  ... {i+1}/{len(sample_dates)} dates processed ({len(all_trades)} trades)")

        sig = generate_signals(data, char_data, entry_date)
        if sig.empty:
            dates_no_signals += 1
            continue
        dates_with_signals += 1
        signal_counts.append(len(sig))

        all_prices = [data[s].loc[entry_date, "close"] for s in data if entry_date in data[s].index]
        idx = all_dates.index(entry_date)
        if idx >= 20 and all_prices:
            past_date = all_dates[idx - 20]
            past_prices = [data[s].loc[past_date, "close"] for s in data if past_date in data[s].index]
            ret_20d = (np.mean(all_prices) / np.mean(past_prices) - 1) * 100 if past_prices else 0
        else:
            ret_20d = 0
        regime = _classify_regime(ret_20d)

        horizon_data = build_horizon_results(data, sig, entry_date, [horizon])
        trades = build_portfolio(sig, horizon_data, horizon, regime, capital)
        all_trades.extend(trades)

    if not all_trades:
        print(f"\n  No trades generated. Cannot produce accuracy report.")
        return

    df = pd.DataFrame(all_trades)
    wins = df[df["return_pct"] > 0]
    losses = df[df["return_pct"] <= 0]
    trade_returns = df["return_pct"]
    hit_rate = (trade_returns > 0).mean() * 100

    print(f"\n{'='*70}")
    print(f"  ACCURACY REPORT")
    print(f"{'='*70}")
    print(f"\n  VALIDATION OVERVIEW")
    print(f"  {'Sample dates':.<30} {len(sample_dates)}")
    print(f"  {'Dates with signals':.<30} {dates_with_signals}")
    print(f"  {'Dates without signals':.<30} {dates_no_signals}")
    print(f"  {'Signal coverage':.<30} {dates_with_signals / len(sample_dates) * 100:.1f}%")
    print(f"  {'Total trades':.<30} {len(df)}")
    print(f"  {'Avg signals/signal-date':.<30} {np.mean(signal_counts):.1f}" if signal_counts else "")

    print(f"\n  HIT RATE & RETURN DISTRIBUTION")
    print(f"  {'Win rate (accuracy)':.<30} {hit_rate:.1f}%")
    print(f"  {'Total wins':.<30} {len(wins)}")
    print(f"  {'Total losses':.<30} {len(losses)}")
    print(f"  {'Avg win':.<30} {wins['return_pct'].mean():+.2f}%" if len(wins) else "")
    print(f"  {'Avg loss':.<30} {losses['return_pct'].mean():+.2f}%" if len(losses) else "")
    print(f"  {'Avg return (expectancy)':.<30} {trade_returns.mean():+.2f}%")
    print(f"  {'Median return':.<30} {trade_returns.median():+.2f}%")
    print(f"  {'Std dev of returns':.<30} {trade_returns.std():.2f}%")
    print(f"  {'Best trade':.<30} {trade_returns.max():+.2f}%")
    print(f"  {'Worst trade':.<30} {trade_returns.min():+.2f}%")
    print(f"  {'Skewness':.<30} {trade_returns.skew():.2f}")
    print(f"  {'Kurtosis':.<30} {trade_returns.kurtosis():.2f}")

    pl_ratio = wins["return_pct"].sum() / abs(losses["return_pct"].sum()) if len(losses) else float("inf")
    up_avg = wins["return_pct"].mean() if len(wins) else 0
    dn_avg = losses["return_pct"].mean() if len(losses) else 0
    win_loss_ratio = abs(up_avg / dn_avg) if dn_avg != 0 else float("inf")
    print(f"  {'Profit factor':.<30} {'INF' if pl_ratio == float('inf') else f'{pl_ratio:.2f}'}")
    print(f"  {'Win/Loss magnitude ratio':.<30} {'INF' if win_loss_ratio == float('inf') else f'{win_loss_ratio:.2f}'}")

    conf_95_lo = trade_returns.mean() - 1.96 * trade_returns.std() / np.sqrt(len(trade_returns))
    conf_95_hi = trade_returns.mean() + 1.96 * trade_returns.std() / np.sqrt(len(trade_returns))
    print(f"  {'95% CI of mean return':.<30} [{conf_95_lo:+.2f}%, {conf_95_hi:+.2f}%]")

    print(f"\n  ACCURACY BY REGIME")
    print(f"  {'Regime':<18} {'Trades':>7} {'Win%':>7} {'AvgRet':>8} {'Best':>8} {'Worst':>8} {'P.Factor':>9}")
    print(f"  {'-'*17:<18} {'-'*6:>7} {'-'*6:>7} {'-'*7:>8} {'-'*7:>8} {'-'*7:>8} {'-'*8:>9}")
    for regime_label in ["Strong Bull", "Bull", "Sideways", "Bear", "Crash"]:
        sub = df[df["regime"] == regime_label]
        if sub.empty:
            continue
        w = sub[sub["return_pct"] > 0]
        l_ = sub[sub["return_pct"] <= 0]
        pf = w["return_pct"].sum() / abs(l_["return_pct"].sum()) if len(l_) else float("inf")
        pf_s = "INF" if pf == float("inf") else f"{pf:.2f}"
        print(f"  {regime_label:<18} {len(sub):>7} {len(w)/len(sub)*100:>6.1f}% {sub['return_pct'].mean():>+7.2f}% {sub['return_pct'].max():>+7.2f}% {sub['return_pct'].min():>+7.2f}% {pf_s:>9}")

    print(f"\n  SIGNAL QUALITY")
    top_quartile = trade_returns.quantile(0.75)
    bot_quartile = trade_returns.quantile(0.25)
    print(f"  {'Upper quartile (Q3)':.<30} {top_quartile:+.2f}%")
    print(f"  {'Lower quartile (Q1)':.<30} {bot_quartile:+.2f}%")
    print(f"  {'Interquartile range':.<30} {top_quartile - bot_quartile:.2f}%")

    # Run-length analysis
    cons_loss = 0
    max_cons_loss = 0
    cons_win = 0
    max_cons_win = 0
    for ret in trade_returns:
        if ret <= 0:
            cons_loss += 1
            cons_win = 0
            max_cons_loss = max(max_cons_loss, cons_loss)
        else:
            cons_win += 1
            cons_loss = 0
            max_cons_win = max(max_cons_win, cons_win)
    print(f"  {'Max consecutive wins':.<30} {max_cons_win}")
    print(f"  {'Max consecutive losses':.<30} {max_cons_loss}")

    # Repeat accuracy (trade 1 vs subsequent trades on same date)
    first_wr = 0.0
    later_wr = 0.0
    multi_signal_dates = df.groupby("entry_date").filter(lambda x: len(x) > 1)
    if not multi_signal_dates.empty:
        first_trades = multi_signal_dates.groupby("entry_date").nth(0)
        later_trades = multi_signal_dates.groupby("entry_date").nth(1)
        if not first_trades.empty:
            first_wr = (first_trades["return_pct"] > 0).mean() * 100
            print(f"  {'Rank-1 signal win rate':.<30} {first_wr:.1f}%")
        if not later_trades.empty:
            later_wr = (later_trades["return_pct"] > 0).mean() * 100
            print(f"  {'Rank-2+ signals win rate':.<30} {later_wr:.1f}%")

    print(f"\n{'='*70}")
    print(f"  VERDICT")
    print(f"{'='*70}")
    gates_pass = 0
    gates_total = 5
    g1 = hit_rate > 40
    g2 = trade_returns.mean() > 0
    g3 = pl_ratio > 1.5
    g4 = len(df) >= 100
    g5 = abs(dn_avg) < abs(up_avg) if len(wins) and len(losses) else True
    print(f"  {'Gate 1: Win rate > 40%':.<30} {'PASS' if g1 else 'FAIL'} ({hit_rate:.1f}%)")
    print(f"  {'Gate 2: Positive expectancy':.<30} {'PASS' if g2 else 'FAIL'} ({trade_returns.mean():+.2f}%)")
    print(f"  {'Gate 3: Profit factor > 1.5':.<30} {'PASS' if g3 else 'FAIL'} ({pl_ratio:.2f})")
    print(f"  {'Gate 4: At least 100 trades':.<30} {'PASS' if g4 else 'FAIL'} ({len(df)})")
    print(f"  {'Gate 5: Avg win > |avg loss|':.<30} {'PASS' if g5 else 'FAIL'} ({up_avg:+.2f}% vs {dn_avg:+.2f}%)")
    print(f"  {'Gates passed':.<30} {sum([g1,g2,g3,g4,g5])}/{gates_total}")
    print(f"  {'Recommendation':.<30} {'Ready for paper trading' if sum([g1,g2,g3,g4,g5]) >= 4 else 'More research needed'}")

    if output:
        os.makedirs(os.path.dirname(output), exist_ok=True)
        html = generate_html(
            universe_slug, years, horizon, capital, sample_interval,
            all_dates, sample_dates, dates_with_signals, dates_no_signals, signal_counts,
            df, wins, losses, trade_returns, hit_rate, pl_ratio, up_avg, dn_avg,
            win_loss_ratio, conf_95_lo, conf_95_hi, max_cons_win, max_cons_loss,
            first_wr, later_wr, g1, g2, g3, g4, g5,
        )
        with open(output, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\n  HTML report saved: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Walk-forward validation for any universe")
    parser.add_argument("--universe", "-u", default="nifty50", help="Universe slug (default: nifty50)")
    parser.add_argument("--years", type=int, default=3, help="Years of history (default: 3)")
    parser.add_argument("--horizon", type=int, default=21, help="Forward horizon in trading days (default: 21)")
    parser.add_argument("--capital", type=float, default=10_000_000, help="Capital (default: 10000000)")
    parser.add_argument("--interval", type=int, default=5, help="Sample every N trading days (default: 5)")
    parser.add_argument("--output", default=None, help="Save HTML report to file")
    args = parser.parse_args()

    validate(args.universe, args.years, args.horizon, args.capital, args.interval, args.output)
