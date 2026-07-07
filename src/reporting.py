"""Beautiful HTML report generation for daily scan and forward check."""

from __future__ import annotations

import pandas as pd

TEMPLATE_CSS = """
:root {
  --bg: #F8F9FA;
  --surface: #FFFFFF;
  --slate: #1E293B;
  --sage: #2E6F40;
  --navy: #0F172A;
  --amber: #D97706;
  --border: #E2E8F0;
  --muted: #64748B;
  --text: #1E293B;
  --text-soft: #475569;
  --positive: #2E6F40;
  --negative: #DC2626;
  --shadow: 0 4px 20px -2px rgba(0,0,0,0.05);
}
[data-theme="dark"] {
  --bg: #121314;
  --surface: #1A1B1E;
  --slate: #E2E8F0;
  --sage: #4ADE80;
  --navy: #38BDF8;
  --amber: #FBBF24;
  --border: #2A2B2D;
  --muted: #94A3B8;
  --text: #E2E8F0;
  --text-soft: #CBD5E1;
  --positive: #4ADE80;
  --negative: #F87171;
  --shadow: 0 4px 20px -2px rgba(0,0,0,0.4);
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  padding: 24px;
  transition: background 0.3s, color 0.3s;
}
.theme-toggle {
  position: fixed; top: 16px; right: 16px; z-index: 100;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 14px; cursor: pointer;
  font-size: 13px; color: var(--text-soft);
  box-shadow: var(--shadow);
}
.theme-toggle:hover { border-color: var(--sage); }
.container { max-width: 1200px; margin: 0 auto; }
header {
  display: flex; justify-content: space-between; align-items: flex-start;
  margin-bottom: 28px; flex-wrap: wrap; gap: 16px;
}
header h1 {
  font-family: 'Playfair Display', Georgia, serif;
  font-size: 28px; font-weight: 700; color: var(--slate);
  letter-spacing: -0.3px;
}
header .meta { color: var(--muted); font-size: 14px; margin-top: 4px; }
.exec-summary {
  display: grid; grid-template-columns: 2fr 1fr; gap: 16px;
  margin-bottom: 28px;
}
.exec-summary .context-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px 24px; box-shadow: var(--shadow);
}
.exec-summary .context-card h3 {
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 11px; text-transform: uppercase; letter-spacing: 1px;
  color: var(--muted); margin-bottom: 12px;
}
.exec-summary .context-card .stat-row {
  display: flex; flex-wrap: wrap; gap: 20px 32px;
}
.exec-summary .context-card .stat {
  display: flex; flex-direction: column;
}
.exec-summary .context-card .stat .label {
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
  color: var(--muted);
}
.exec-summary .context-card .stat .value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 20px; font-weight: 600; color: var(--slate);
  line-height: 1.3;
}
.exec-summary .context-card .stat .value.bullish { color: var(--positive); }
.exec-summary .context-card .stat .value.bearish { color: var(--negative); }
.kpi-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
}
.kpi-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 16px; box-shadow: var(--shadow);
  display: flex; flex-direction: column;
}
.kpi-card .kpi-label {
  font-size: 10px; text-transform: uppercase; letter-spacing: 0.8px;
  color: var(--muted);
}
.kpi-card .kpi-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 22px; font-weight: 700; color: var(--slate);
  line-height: 1.2; margin-top: 4px;
}
.kpi-card .kpi-sub {
  font-size: 12px; color: var(--text-soft); margin-top: 2px;
}
section { margin-bottom: 28px; }
section h2 {
  font-family: 'Playfair Display', Georgia, serif;
  font-size: 20px; font-weight: 600; color: var(--slate);
  margin-bottom: 14px; padding-bottom: 8px;
  border-bottom: 2px solid var(--border);
}
.data-table-wrap {
  overflow-x: auto; border: 1px solid var(--border);
  border-radius: 10px; background: var(--surface); box-shadow: var(--shadow);
}
table.data-table {
  width: 100%; border-collapse: collapse; font-size: 14px;
  table-layout: fixed;
}
table.data-table thead th {
  background: var(--bg); color: var(--muted);
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.8px;
  padding: 12px 14px; text-align: right; border-bottom: 1px solid var(--border);
  font-weight: 600;
}
table.data-table thead th:first-child { text-align: left; }
table.data-table tbody td {
  padding: 10px 14px; text-align: right; border-bottom: 1px solid var(--border);
  color: var(--text);
}
table.data-table tbody td:first-child { text-align: left; font-weight: 600; }
table.data-table tbody tr:nth-child(even) { background: rgba(0,0,0,0.015); }
table.data-table tbody tr:hover { background: rgba(46,111,64,0.04); }
table.data-table tbody td.mono { font-family: 'JetBrains Mono', monospace; font-size: 13px; }
table.data-table td.positive { color: var(--positive); font-weight: 600; }
table.data-table td.negative { color: var(--negative); font-weight: 600; }
.micro-bar {
  display: inline-block; height: 6px; border-radius: 3px;
  background: var(--border); width: 60px; vertical-align: middle;
  margin-right: 6px; overflow: hidden;
}
.micro-bar .fill { height: 100%; border-radius: 3px; transition: width 0.6s; }
.micro-bar .fill.positive { background: var(--positive); }
.micro-bar .fill.negative { background: var(--negative); }
.badge {
  display: inline-block; padding: 2px 10px; border-radius: 12px;
  font-size: 11px; font-weight: 600; letter-spacing: 0.3px;
}
.badge.bullish { background: rgba(46,111,64,0.1); color: var(--positive); }
.badge.bearish { background: rgba(220,38,38,0.1); color: var(--negative); }
.badge.sideways { background: rgba(217,119,6,0.1); color: var(--amber); }
.legend {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 20px; margin-top: 14px;
  font-size: 13px; color: var(--text-soft); line-height: 1.8;
  box-shadow: var(--shadow);
}
.legend strong { color: var(--text); }
footer {
  margin-top: 36px; padding-top: 16px; border-top: 1px solid var(--border);
  font-size: 12px; color: var(--muted); text-align: center;
}
@media (max-width: 768px) {
  .exec-summary { grid-template-columns: 1fr; }
  .kpi-grid { grid-template-columns: 1fr 1fr; }
  header h1 { font-size: 22px; }
}
@media print {
  body { background: #fff; padding: 0; }
  .theme-toggle { display: none; }
  .container { max-width: 100%; }
  table.data-table tbody tr:nth-child(even) { background: #f8f9fa; }
}
"""


def _signal_rows_html(signals: pd.DataFrame) -> str:
    rows = ""
    for _, r in signals.iterrows():
        conv = r.get("conviction", 0)
        conv_pct = min(conv / 5 * 100, 100)
        rows += f"""<tr>
          <td>{r['rank']}</td>
          <td class="mono">{r['close']:.2f}</td>
          <td class="mono">{r['conviction']:.4f}</td>
          <td><div class="micro-bar"><div class="fill positive" style="width:{conv_pct:.0f}%"></div></div></td>
        </tr>"""
    return rows


def daily_scan_html(
    date_str: str,
    signals: pd.DataFrame,
    regime: dict,
    targets: dict,
    universe_name: str,
    profit_target_1: float = 0.12,
    profit_target_2: float = 0.18,
    hard_stop: float = -0.08,
    trail_activate: float = 0.10,
    trail_distance: float = 0.12,
) -> str:
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    trend_cls = regime.get("trend_label", "sideways").lower()
    signal_count = len(signals)

    target_rows = ""
    for _, r in signals.iterrows():
        sym = r["symbol"]
        t = targets.get(sym, {})
        ep = t.get("entry", r["close"])
        ret_t1 = (t.get("target1", ep) / ep - 1) * 100
        ret_t2 = (t.get("target2", ep) / ep - 1) * 100
        ret_stop = (t.get("hard_stop", ep) / ep - 1) * 100
        ret_trail = (t.get("trail_stop", ep) / ep - 1) * 100
        target_rows += f"""<tr>
          <td style="font-weight:600">{sym}</td>
          <td class="mono">{ep:.2f}</td>
          <td class="mono">{t.get("target1", 0):.2f}</td>
          <td class="mono positive">{ret_t1:+.1f}%</td>
          <td class="mono">{t.get("target2", 0):.2f}</td>
          <td class="mono positive">{ret_t2:+.1f}%</td>
          <td class="mono">{t.get("hard_stop", 0):.2f}</td>
          <td class="mono negative">{ret_stop:+.1f}%</td>
          <td class="mono">{t.get("trail_trigger", 0):.2f}</td>
          <td class="mono">{t.get("trail_stop", 0):.2f}</td>
          <td class="mono negative">{ret_trail:+.1f}%</td>
          <td class="mono">{r.get("conviction", 0):.4f}</td>
          <td><div class="micro-bar"><div class="fill positive" style="width:{min(r.get("conviction",0)/5*100,100):.0f}%"></div></div></td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Daily Scan — {date_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>{TEMPLATE_CSS}</style>
</head><body>
<button class="theme-toggle" onclick="document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark'">Toggle Theme</button>
<div class="container">
<header><div><h1>Daily Scan</h1><div class="meta">{date_str} · {universe_name} · Generated {now}</div>
<div class="meta" style="color:var(--amber);font-size:13px;margin-top:4px">
Entry/exit prices include slippage (0.1%) + brokerage (0.05%). Entry occurs at Friday rebalance.
</div>
</div></header>

<div class="exec-summary">
  <div class="context-card">
    <h3>Market Context</h3>
    <div class="stat-row">
      <div class="stat"><span class="label">Index</span><span class="value">^NSEI @ {regime.get("index_price",0):,.0f}</span></div>
      <div class="stat"><span class="label">Trend 20d</span><span class="value {trend_cls}">{regime.get("trend_label","?")} ({regime.get("trend_20d",0):+.2f}%)</span></div>
      <div class="stat"><span class="label">Volatility</span><span class="value">ATR {regime.get("atr_pct",0)}%</span></div>
    </div>
  </div>
  <div class="kpi-grid">
    <div class="kpi-card"><span class="kpi-label">Signals</span><span class="kpi-value">{signal_count}</span><span class="kpi-sub">next entry: Friday</span></div>
    <div class="kpi-card"><span class="kpi-label">Universe</span><span class="kpi-value" style="font-size:16px">{universe_name}</span><span class="kpi-sub">{regime.get("n_stocks","?")} stocks</span></div>
  </div>
</div>

<section><h2>Signals with Exit Levels</h2>
<div class="data-table-wrap">
<table class="data-table">
<thead><tr>
  <th scope="col">Symbol</th><th scope="col">Entry*</th>
  <th scope="col">Target1</th><th scope="col">Ret1</th>
  <th scope="col">Target2</th><th scope="col">Ret2</th>
  <th scope="col">HardStop</th><th scope="col">StopRet</th>
  <th scope="col">TrailTrig</th><th scope="col">TrailStop</th><th scope="col">TrailRet</th>
  <th scope="col">Conviction</th><th scope="col">Score</th>
</tr></thead>
<tbody>{target_rows}</tbody>
</table></div>
<div class="legend">
<strong>Exit Rules:</strong>
Target1 = +{profit_target_1*100:.0f}% (sell half)&ensp;·&ensp;
Target2 = +{profit_target_2*100:.0f}%&ensp;·&ensp;
HardStop = {abs(hard_stop)*100:.0f}%&ensp;·&ensp;
Trailing Stop = activate at +{trail_activate*100:.0f}%, trail {-abs(trail_distance)*100:.0f}% from high&ensp;·&ensp;
Time Stop = 20 trading days
</div>
<div class="legend" style="margin-top:8px;color:var(--muted);font-size:12px">
*All prices include transaction costs (slippage + brokerage). Entry occurs at Friday close on rebalance day.
</div>
</section>

<footer>Daily Scan Report · AI Quantitative Researcher</footer>
</div></body></html>"""


def forward_check_html(
    entry_date: pd.Timestamp,
    sig: pd.DataFrame,
    horizon_data: dict,
    horizons: list,
    capital: float,
) -> str:
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    signal_count = len(sig)

    signal_rows = ""
    for _, r in sig.iterrows():
        conv = r.get("conviction", 0)
        conv_pct = min(conv / 5 * 100, 100)
        signal_rows += f"""<tr>
          <td style="font-weight:600">{r['symbol']}</td>
          <td class="mono">{r['close']:.2f}</td>
          <td class="mono">{r['conviction']:.4f}</td>
          <td><div class="micro-bar"><div class="fill positive" style="width:{conv_pct:.0f}%"></div></div></td>
        </tr>"""

    horizon_sections = ""
    for h in horizons:
        hd = horizon_data.get(h, {})
        df = hd.get("df", pd.DataFrame())
        if df.empty:
            horizon_sections += f"""<section><h2>{h} Trading Days</h2><p style="color:var(--muted)">Insufficient forward data.</p></section>"""
            continue
        exit_date = hd.get("exit_date")
        dates = hd.get("dates", [])
        n_days = len(dates) - 1 if len(dates) > 1 else 0
        cal_days = (exit_date - entry_date).days if exit_date else 0
        winners_df = df[df["return_pct"] > 0] if not df.empty else pd.DataFrame()
        losers_df = df[df["return_pct"] < 0] if not df.empty else pd.DataFrame()
        n_winners = len(winners_df)
        n_total = len(df)
        win_rate = n_winners / n_total * 100 if n_total > 0 else 0
        avg_ret = df["return_pct"].mean() if not df.empty else 0
        best_row = df.loc[df["return_pct"].idxmax()] if not df.empty and df["return_pct"].notna().any() else None
        worst_row = df.loc[df["return_pct"].idxmin()] if not df.empty and df["return_pct"].notna().any() else None

        trade_rows = ""
        for _, r in df.iterrows():
            ret = r["return_pct"]
            cls = "positive" if ret is not None and ret > 0 else "negative" if ret is not None else ""
            ret_s = f"{ret:+.2f}%" if ret is not None else "N/A"
            min_s = f"{r['min_intra_pct']:+.2f}%" if r["min_intra_pct"] is not None else "N/A"
            trade_rows += f"""<tr>
              <td style="font-weight:600">{r['symbol']}</td>
              <td class="mono">{r['entry_price']:.2f}</td>
              <td class="mono">{r['exit_price']:.2f}</td>
              <td class="mono {cls}">{ret_s}</td>
              <td class="mono">{min_s}</td>
              <td><div class="micro-bar"><div class="fill {'positive' if ret and ret>0 else 'negative'}" style="width:{min(abs(ret or 0)/30*100,100):.0f}%"></div></div></td>
            </tr>"""

        summary_bars = ""
        if n_total > 0:
            wr_pct = win_rate / 100
            summary_bars = f"""<div style="display:flex;gap:8px;align-items:center;margin:8px 0">
              <span style="font-size:13px;color:var(--muted)">Win Rate</span>
              <div class="micro-bar" style="width:120px"><div class="fill positive" style="width:{wr_pct*100:.0f}%"></div></div>
              <span class="mono" style="font-size:13px">{win_rate:.0f}%</span>
            </div>"""

        best_s = f"{best_row['symbol']} ({best_row['return_pct']:+.2f}%)" if best_row is not None else "N/A"
        worst_s = f"{worst_row['symbol']} ({worst_row['return_pct']:+.2f}%)" if worst_row is not None else "N/A"

        horizon_sections += f"""<section><h2>{h} Trading Days</h2>
<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px">
  <span style="font-size:13px;color:var(--muted)">Entry {entry_date.strftime('%Y-%m-%d')} → Exit {exit_date.strftime('%Y-%m-%d') if exit_date else '?'} · {cal_days} cal days · {n_days} trading days</span>
</div>
<div class="data-table-wrap">
<table class="data-table">
<thead><tr><th scope="col">Symbol</th><th scope="col">Entry</th><th scope="col">Exit</th><th scope="col">Return</th><th scope="col">Min Intra</th><th scope="col">Magnitude</th></tr></thead>
<tbody>{trade_rows}</tbody>
</table></div>
<div style="display:flex;gap:24px;flex-wrap:wrap;margin-top:10px;font-size:13px;color:var(--text-soft)">
  <span><strong style="color:var(--text)">Winners:</strong> {n_winners}/{n_total}</span>
  <span><strong style="color:var(--text)">Avg Return:</strong> {avg_ret:+.2f}%</span>
  <span><strong style="color:var(--text)">Best:</strong> {best_s}</span>
  <span><strong style="color:var(--text)">Worst:</strong> {worst_s}</span>
</div>
{summary_bars}
</section>"""

    cross_rows = ""
    all_rets: dict = {}
    for _, row in sig.iterrows():
        sym = row["symbol"]
        all_rets[sym] = {}
        for h in horizons:
            for r in horizon_data.get(h, {}).get("results", []):
                if r["symbol"] == sym and r["return_pct"] is not None:
                    all_rets[sym][h] = r["return_pct"]
    for sym in all_rets:
        rets = all_rets[sym]
        vals = [v for v in rets.values() if v is not None]
        avg = sum(vals) / len(vals) if vals else 0
        cells = ""
        for h in horizons:
            if h in rets:
                rv = rets[h]
                cls = "positive" if rv > 0 else "negative"
                cells += f'<td class="mono {cls}">{rv:+.2f}%</td>'
            else:
                cells += '<td class="mono" style="color:var(--muted)">N/A</td>'
        avg_cls = "positive" if avg > 0 else "negative"
        cross_rows += f"<tr><td style='font-weight:600'>{sym}</td>{cells}<td class='mono {avg_cls}'>{avg:+.2f}%</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Forward Return Report — {entry_date.strftime('%Y-%m-%d')}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>{TEMPLATE_CSS}</style>
</head><body>
<button class="theme-toggle" onclick="document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark'">Toggle Theme</button>
<div class="container">
<header><div><h1>Forward Return Report</h1><div class="meta">Entry {entry_date.strftime('%Y-%m-%d')} ({entry_date.strftime('%A')}) · Generated {now}</div></div></header>

<div class="exec-summary">
  <div class="context-card">
    <h3>Trade Context</h3>
    <div class="stat-row">
      <div class="stat"><span class="label">Entry Date</span><span class="value">{entry_date.strftime('%Y-%m-%d')}</span></div>
      <div class="stat"><span class="label">Day</span><span class="value">{entry_date.strftime('%A')}</span></div>
      <div class="stat"><span class="label">Capital</span><span class="value">₹{capital:,.0f}</span></div>
    </div>
  </div>
  <div class="kpi-grid">
    <div class="kpi-card"><span class="kpi-label">Signals</span><span class="kpi-value">{signal_count}</span><span class="kpi-sub">stocks triggered</span></div>
    <div class="kpi-card"><span class="kpi-label">Horizons</span><span class="kpi-value" style="font-size:16px">{', '.join(f'{h}d' for h in horizons)}</span><span class="kpi-sub">trading days</span></div>
  </div>
</div>

<section><h2>Entry Signals</h2>
<div class="data-table-wrap">
<table class="data-table">
<thead><tr><th scope="col">Symbol</th><th scope="col">Entry Price</th><th scope="col">Conviction</th><th scope="col">Score</th></tr></thead>
<tbody>{signal_rows}</tbody>
</table></div>
</section>

{horizon_sections}

<section><h2>Cross-Horizon Comparison</h2>
<div class="data-table-wrap">
<table class="data-table">
<thead><tr><th scope="col">Symbol</th>{"".join(f'<th scope="col">{h}d</th>' for h in horizons)}<th scope="col">Avg</th></tr></thead>
<tbody>{cross_rows}</tbody>
</table></div>
</section>

<footer>Forward Return Check · AI Quantitative Researcher</footer>
</div></body></html>"""
