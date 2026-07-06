"""Daily scan: find actionable signals in any universe, with exit levels.

Usage:
    python daily_scan.py                                # NIFTY 50, today
    python daily_scan.py --universe niftymidcap150      # Midcap 150, today
    python daily_scan.py --date 2026-06-01 --output report.html
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yfinance as yf

from src.backtest import (
    HARD_STOP,
    PROFIT_TARGET_1,
    PROFIT_TARGET_2,
    TRAIL_ACTIVATE,
    generate_signals,
)
from src.db import DB_PATH, load_data, load_universe
from src.features import precompute_all_characteristics

NIFTY_INDEX_TICKER = "^NSEI"


def compute_regime() -> dict:
    df = yf.download(NIFTY_INDEX_TICKER, period="6mo", progress=False, auto_adjust=True)
    if df.empty:
        return {"index_price": 0, "trend_20d": 0, "trend_label": "Unknown", "atr_pct": 0}
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]
    close = df["close"]
    price = close.iloc[-1]
    ret_20d = close.iloc[-1] / close.iloc[-min(21, len(close))] - 1 if len(close) >= 21 else 0
    atr = (df["high"] - df["low"]).rolling(20).mean().iloc[-1]
    atr_pct = atr / price * 100 if price > 0 else 0
    if ret_20d > 0.03:
        label = "Bullish"
    elif ret_20d < -0.03:
        label = "Bearish"
    else:
        label = "Sideways"
    return {"index_price": round(price, 2), "trend_20d": round(ret_20d * 100, 2), "trend_label": label, "atr_pct": round(atr_pct, 2)}


def generate_html(date_str, signals, regime, targets, universe_name):
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    signal_rows = ""
    for _, r in signals.iterrows():
        sym = r["symbol"]
        t = targets.get(sym, {})
        signal_rows += f"""
        <tr>
            <td>{r['rank']}</td>
            <td>{sym}</td>
            <td>{r['close']:.2f}</td>
            <td>{t.get('target1', 0):.2f}</td>
            <td>{t.get('target2', 0):.2f}</td>
            <td>{t.get('hard_stop', 0):.2f}</td>
            <td>{t.get('trail_trigger', 0):.2f}</td>
            <td>{r['conviction']:.4f}</td>
        </tr>"""
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Daily Scan - {date_str}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 30px; background: #f5f5f5; color: #333; }}
.container {{ max-width: 1100px; margin: auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
h1 {{ margin: 0 0 5px; color: #1a1a2e; }}
.subtitle {{ color: #666; font-size: 14px; margin-bottom: 20px; }}
.regime-bar {{ display: flex; gap: 20px; margin-bottom: 24px; flex-wrap: wrap; }}
.regime-item {{ background: #f8f9fa; padding: 10px 18px; border-radius: 6px; }}
.regime-item label {{ display: block; font-size: 11px; color: #888; text-transform: uppercase; }}
.regime-item .value {{ font-size: 16px; font-weight: 600; color: #1a1a2e; }}
.bullish .value {{ color: #2d7d2d; }}
.bearish .value {{ color: #c0392b; }}
table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }}
th, td {{ padding: 10px 12px; text-align: right; border-bottom: 1px solid #e9ecef; }}
th {{ background: #f8f9fa; font-weight: 600; color: #555; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
tr:hover {{ background: #f1f3f5; }}
.levels-note {{ background: #f8f9fa; padding: 10px 16px; border-radius: 6px; font-size: 13px; color: #666; margin-top: 16px; }}
.footer {{ margin-top: 30px; padding-top: 16px; border-top: 1px solid #e9ecef; font-size: 12px; color: #999; }}
</style></head><body><div class="container">
<h1>Daily Scan Report</h1><div class="subtitle">Generated {now}</div>
<div class="regime-bar">
<div class="regime-item {regime['trend_label'].lower()}"><label>Index</label><div class="value">{NIFTY_INDEX_TICKER} @ {regime['index_price']}</div></div>
<div class="regime-item {regime['trend_label'].lower()}"><label>Trend (20d)</label><div class="value">{regime['trend_label']} ({regime['trend_20d']:+.2f}%)</div></div>
<div class="regime-item"><label>Volatility (ATR)</label><div class="value">{regime['atr_pct']}%</div></div>
<div class="regime-item"><label>Universe</label><div class="value">{universe_name}</div></div>
<div class="regime-item"><label>Signals</label><div class="value">{len(signals)}</div></div>
</div>
<h2>Actionable Signals</h2>
<table>
<tr><th>Symbol</th><th>Entry</th><th>Target1</th><th>Target2</th><th>Stop</th><th>Trail Trig</th><th>Conviction</th></tr>
{signal_rows}
</table>
<div class="levels-note">
<strong>Exit Levels:</strong> Target1=+{PROFIT_TARGET_1*100:.0f}%, Target2=+{PROFIT_TARGET_2*100:.0f}%, HardStop={abs(HARD_STOP)*100:.0f}%, TrailTrigger=+{TRAIL_ACTIVATE*100:.0f}% from entry, TimeStop=20 trading days
</div>
<div class="footer">Daily Scan Tool</div>
</div></body></html>"""
    return html


def scan(universe_slug_or_path: str, date_str: str | None = None, output: str | None = None):
    config = load_universe(universe_slug_or_path)
    slug = config.get("slug", Path(universe_slug_or_path).stem)
    universe_name = config.get("name", slug)
    symbols = config["symbols"]

    if date_str:
        scan_date = pd.Timestamp(date_str)
    else:
        scan_date = pd.Timestamp.now().normalize()
        if scan_date.weekday() >= 5:
            scan_date -= pd.Timedelta(days=scan_date.weekday() - 4)

    print(f"\n{'='*70}")
    print(f"  DAILY SCAN REPORT")
    print(f"  Date:     {scan_date.date()} ({scan_date.strftime('%A')})")
    print(f"  Universe: {universe_name} ({len(symbols)} stocks)")
    print(f"{'='*70}")

    print(f"\n  Market Regime...")
    regime = compute_regime()
    print(f"  {NIFTY_INDEX_TICKER} @ {regime['index_price']} | {regime['trend_label']} ({regime['trend_20d']:+.2f}% 20d) | ATR {regime['atr_pct']}%")

    print(f"  Loading data...")
    df_all = load_data(universe_slug_or_path)
    data: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        sub = df_all[df_all["symbol"] == sym].copy()
        if sub.empty:
            continue
        sub = sub.set_index("date")
        sub.index = pd.DatetimeIndex(sub.index)
        data[sym] = sub
    print(f"  Loaded {len(data)}/{len(symbols)} stocks")

    print(f"  Computing characteristics...")
    char_data = precompute_all_characteristics(data, window=20)

    if scan_date not in next(iter(char_data.values()), pd.DataFrame()).index:
        available = sorted(set(d for s in char_data for d in char_data[s].index))
        closest = [d for d in available if d >= scan_date]
        if not closest:
            print(f"  No trading data on or after {scan_date.date()}")
            return
        scan_date = closest[0]
        print(f"  Adjusted to nearest trading day: {scan_date.date()}")

    sig = generate_signals(data, char_data, scan_date)
    if sig.empty:
        print(f"\n  No signals on {scan_date.date()}.")
        return

    targets = {}
    for _, r in sig.iterrows():
        ep = r["close"]
        targets[r["symbol"]] = {
            "target1": round(ep * (1 + PROFIT_TARGET_1), 2),
            "target2": round(ep * (1 + PROFIT_TARGET_2), 2),
            "hard_stop": round(ep * (1 + HARD_STOP), 2),
            "trail_trigger": round(ep * (1 + TRAIL_ACTIVATE), 2),
        }

    print(f"\n  Signals: {len(sig)}")
    print(f"  {'Rank':<5} {'Symbol':<18} {'Entry':>9} {'Target1':>9} {'Target2':>9} {'Stop':>9} {'TrailTrg':>9} {'Conviction':>10}")
    print(f"  {'-'*4:<5} {'-'*17:<18} {'-'*8:>9} {'-'*8:>9} {'-'*8:>9} {'-'*8:>9} {'-'*8:>9} {'-'*9:>10}")
    for _, r in sig.iterrows():
        t = targets[r["symbol"]]
        print(f"  {r['rank']:<5} {r['symbol']:<18} {r['close']:>9.2f} {t['target1']:>9.2f} {t['target2']:>9.2f} {t['hard_stop']:>9.2f} {t['trail_trigger']:>9.2f} {r['conviction']:>10.4f}")

    print(f"\n  Exit Levels: Target1=+{PROFIT_TARGET_1*100:.0f}%  Target2=+{PROFIT_TARGET_2*100:.0f}%  "
          f"HardStop={abs(HARD_STOP)*100:.0f}%  TrailTrigger=+{TRAIL_ACTIVATE*100:.0f}% from entry high  TimeStop=20d")
    print(f"{'='*70}\n")

    if output:
        html = generate_html(scan_date.strftime("%Y-%m-%d"), sig, regime, targets, universe_name)
        with open(output, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  HTML report saved: {output}")


def main():
    parser = argparse.ArgumentParser(description="Daily scan for actionable signals")
    parser.add_argument("--universe", "-u", default="nifty50",
                        help="Universe slug or path to JSON (default: nifty50)")
    parser.add_argument("--date", default=None,
                        help="Override date (YYYY-MM-DD). Default: today")
    parser.add_argument("--output", default=None,
                        help="Save HTML report to file")
    args = parser.parse_args()
    scan(args.universe, args.date, args.output)


if __name__ == "__main__":
    main()
