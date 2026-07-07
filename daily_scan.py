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
    SLIPPAGE,
    BROKERAGE,
    TRAIL_ACTIVATE,
    TRAIL_DISTANCE,
    generate_signals,
)
from src.db import DB_PATH, load_data, load_universe
from src.features import precompute_all_characteristics
from src.reporting import daily_scan_html

NIFTY_INDEX_TICKER = "^NSEI"

ENTRY_COST_MULT = 1 + SLIPPAGE + BROKERAGE
EXIT_COST_MULT = 1 - SLIPPAGE - BROKERAGE


REGIME_RULES = [
    # (20d_return_min, 20d_return_max, label, max_positions, action, note)
    (8,    float("inf"), "Strong Bull", 2, "Reduce", "Rare regime. Trades infrequent."),
    (3,    8,             "Bull",        1, "Skip or 1", "25% win rate. Avoid."),
    (-3,   3,             "Sideways",    3, "Full deploy", "Core regime. 59% of market."),
    (-8,   -3,            "Bear",        3, "Full deploy", "Best regime. 78% win rate."),
    (float("-inf"), -8,   "Crash",       3, "Full deploy", "Best regime. 71% win rate."),
]


def compute_regime() -> dict:
    df = yf.download(NIFTY_INDEX_TICKER, period="6mo", progress=False, auto_adjust=True)
    if df.empty:
        return {"index_price": 0, "trend_20d": 0, "trend_label": "Unknown", "atr_pct": 0,
                "max_positions": 1, "action": "Unknown", "regime_note": ""}
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]
    close = df["close"]
    price = close.iloc[-1]
    ret_20d = close.iloc[-1] / close.iloc[-min(21, len(close))] - 1 if len(close) >= 21 else 0
    atr = (df["high"] - df["low"]).rolling(20).mean().iloc[-1]
    atr_pct = atr / price * 100 if price > 0 else 0
    ret_pct = ret_20d * 100

    label = "Unknown"
    max_pos = 1
    action = "Skip"
    note = ""
    for lo, hi, lbl, mp, act, nt in REGIME_RULES:
        if lo <= ret_pct < hi:
            label = lbl
            max_pos = mp
            action = act
            note = nt
            break

    return {
        "index_price": round(price, 2),
        "trend_20d": round(ret_pct, 2),
        "trend_label": label,
        "atr_pct": round(atr_pct, 2),
        "max_positions": max_pos,
        "action": action,
        "regime_note": note,
    }


def generate_html(date_str, signals, regime, targets, universe_name):
    return daily_scan_html(
        date_str, signals, regime, targets, universe_name,
        profit_target_1=PROFIT_TARGET_1, profit_target_2=PROFIT_TARGET_2,
        hard_stop=HARD_STOP, trail_activate=TRAIL_ACTIVATE,
        trail_distance=TRAIL_DISTANCE, max_positions=regime.get("max_positions", 3),
    )


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
    print(f"  >>> RECOMMENDATION: {regime['action']} (max {regime['max_positions']} positions) — {regime['regime_note']}")

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
    rebalance_day = "Friday" if pd.Timestamp.now().weekday() < 4 else "next Friday"
    for _, r in sig.iterrows():
        raw_entry = r["close"]
        entry_price = raw_entry * ENTRY_COST_MULT
        targets[r["symbol"]] = {
            "entry": round(entry_price, 2),
            "target1": round(entry_price * (1 + PROFIT_TARGET_1) * EXIT_COST_MULT, 2),
            "target2": round(entry_price * (1 + PROFIT_TARGET_2) * EXIT_COST_MULT, 2),
            "hard_stop": round(entry_price * (1 + HARD_STOP) * EXIT_COST_MULT, 2),
            "trail_trigger": round(entry_price * (1 + TRAIL_ACTIVATE), 2),
            "trail_stop": round(entry_price * (1 + TRAIL_ACTIVATE) * (1 - TRAIL_DISTANCE), 2),
        }

    print(f"\n  Signals: {len(sig)}")
    print(f"  {'Rank':<5} {'Symbol':<18} {'Entry*':>9} {'Target1':>9} {'Target2':>9} {'Stop':>9} {'Trail@':>9} {'Conv':>10}")
    print(f"  {'-'*4:<5} {'-'*17:<18} {'-'*8:>9} {'-'*8:>9} {'-'*8:>9} {'-'*8:>9} {'-'*8:>9} {'-'*9:>10}")
    for _, r in sig.iterrows():
        t = targets[r["symbol"]]
        print(f"  {r['rank']:<5} {r['symbol']:<18} {t['entry']:>9.2f} {t['target1']:>9.2f} {t['target2']:>9.2f} {t['hard_stop']:>9.2f} {t['trail_trigger']:>9.2f} {r['conviction']:>10.4f}")

    max_pos = regime["max_positions"]
    entries_today = min(len(sig), max_pos)
    print(f"  Max positions today: {max_pos} ({regime['action']}) — entering {entries_today} of {len(sig)} signals")
    print(f"\n  Entry Timing: Signal detected — next entry on {rebalance_day} (rebalance day)")
    print(f"  *Entry price includes slippage ({SLIPPAGE:.1%}) + brokerage ({BROKERAGE:.2%})")
    print(f"  Target1=+{PROFIT_TARGET_1*100:.0f}%  Target2=+{PROFIT_TARGET_2*100:.0f}%  "
          f"HardStop={abs(HARD_STOP)*100:.0f}%  TrailTrigger=+{TRAIL_ACTIVATE*100:.0f}%  "
          f"TrailStop=-{TRAIL_DISTANCE*100:.0f}% from high  TimeStop=20d")
    print(f"  *Target/stop prices include exit costs (slippage + brokerage)")
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
