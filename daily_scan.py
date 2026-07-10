"""Daily scan: find actionable signals in any universe, with exit levels.

Usage:
    python daily_scan.py                                          # NIFTY 50, contrarian, today
    python daily_scan.py --universe niftymidcap150                # Midcap 150, today
    python daily_scan.py --strategy momentum                      # Momentum strategy
    python daily_scan.py --strategy momentum --universe niftymidcap150  # Momentum on Midcap150
    python daily_scan.py --date 2026-06-01 --output report.html
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

from src.backtest import generate_signals, generate_momentum_signals, compute_momentum_stops
from src.config import (
    HARD_STOP, PROFIT_TARGET_1, PROFIT_TARGET_2,
    SLIPPAGE, BROKERAGE, TRAIL_ACTIVATE, TRAIL_DISTANCE,
    REGIME_RULES, MOM_MAX_POSITIONS, MOM_MIN_POSITIONS,
    MOM_STOP_LOSS, MOM_TRAIL_ACTIVATE, MOM_TRAIL_DISTANCE,
    MOM_MIN_VOLUME, MOM_SECTOR_MAX,
)
import json

from src.db import DB_PATH, load_data, load_universe, get_sector_map
from src.features import precompute_all_characteristics
from src.reporting import daily_scan_html, momentum_scan_html

NIFTY_INDEX_TICKER = "^NSEI"

ENTRY_COST_MULT = 1 + SLIPPAGE + BROKERAGE
EXIT_COST_MULT = 1 - SLIPPAGE - BROKERAGE


def compute_regime() -> dict:
    df = yf.download(NIFTY_INDEX_TICKER, period="6mo", progress=False, auto_adjust=True)
    if df.empty:
        return {"index_price": 0, "trend_20d": 0, "trend_label": "Unknown", "atr_pct": 0,
                "max_positions": 1, "action": "Unknown", "regime_note": ""}
    df.index = pd.to_datetime(df.index).tz_localize(None)
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


def generate_html(date_str, signals, regime, targets, universe_name, strategy="contrarian"):
    if strategy == "momentum":
        return momentum_scan_html(
            date_str, signals, regime, targets, universe_name,
            mom_stop_loss=MOM_STOP_LOSS, mom_trail_activate=MOM_TRAIL_ACTIVATE,
            mom_trail_distance=MOM_TRAIL_DISTANCE, max_positions=MOM_MAX_POSITIONS,
        )
    return daily_scan_html(
        date_str, signals, regime, targets, universe_name,
        profit_target_1=PROFIT_TARGET_1, profit_target_2=PROFIT_TARGET_2,
        hard_stop=HARD_STOP, trail_activate=TRAIL_ACTIVATE,
        trail_distance=TRAIL_DISTANCE, max_positions=regime.get("max_positions", 3),
    )


def _save_json(json_path: str | None, scan_date, strategy, sig, targets, regime, sector_map):
    if not json_path:
        return
    signals_json = []
    for _, r in sig.head(50).iterrows():
        sym = r["symbol"]
        t = targets.get(sym, {})
        entry = t.get("entry", r["close"])
        signals_json.append({
            "rank": int(r["rank"]),
            "symbol": sym,
            "close": round(float(r["close"]), 2),
            "entry": float(round(entry, 2)),
            "conviction": round(float(r.get("conviction", 0)), 4),
            "momentum_pct": round(float(r.get("momentum_12m", 0)) * 100, 1),
            "target1": round(t.get("target1", 0), 2),
            "target2": round(t.get("target2", 0), 2),
            "hard_stop": round(t.get("hard_stop", 0), 2),
            "trail_trigger": round(t.get("trail_trigger", 0), 2),
            "trail_stop": round(t.get("trail_stop", 0), 2),
            "sector": sector_map.get(sym, "") if sector_map else "",
        })
    payload = {
        "date": scan_date.strftime("%Y-%m-%d"),
        "strategy": strategy,
        "signal_count": len(sig),
        "max_positions": regime.get("max_positions", 10) if strategy == "contrarian" else MOM_MAX_POSITIONS,
        "regime": {
            "trend_label": regime["trend_label"],
            "trend_20d": regime["trend_20d"],
            "action": regime["action"],
        },
        "signals": signals_json,
    }
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  JSON data saved: {json_path}")


def scan(universe_slug_or_path: str, date_str: str | None = None, output: str | None = None, strategy: str = "contrarian", json_output: str | None = None):
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
    print(f"  Strategy: {strategy.upper()}")
    print(f"{'='*70}")

    print(f"\n  Market Regime...")
    regime = compute_regime()
    crash_mode = regime["trend_20d"] < -8
    print(f"  {NIFTY_INDEX_TICKER} @ {regime['index_price']} | {regime['trend_label']} ({regime['trend_20d']:+.2f}% 20d) | ATR {regime['atr_pct']}%")
    print(f"  >>> RECOMMENDATION: {regime['action']} (max {regime['max_positions']} positions) — {regime['regime_note']}")
    if crash_mode and strategy == "momentum":
        print(f"  *** CRASH MODE: Momentum strategy deactivated. Hold cash. ***")

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

    if strategy == "momentum":
        # Compute average volume for liquidity filter
        all_vol = pd.concat({s: df["volume"] for s, df in data.items() if "volume" in df.columns}, axis=1)
        avg_vol = all_vol.mean() if not all_vol.empty else None

        sig = generate_momentum_signals(data, scan_date, avg_vol_series=avg_vol)
        if sig.empty:
            print(f"\n  No momentum signals on {scan_date.date()}.")
            _save_json(json_output, scan_date, strategy, sig, {}, regime, get_sector_map(universe_slug_or_path))
            sys.exit(1)

        targets = {}
        for _, r in sig.iterrows():
            targets[r["symbol"]] = compute_momentum_stops(r["close"])

        print(f"\n  Momentum Signals: {len(sig)}")
        print(f"  {'Rank':<5} {'Symbol':<18} {'Momentum':>10} {'Price':>9} {'Entry*':>9} {'Stop':>9} {'Trail@':>9}")
        print(f"  {'-'*4:<5} {'-'*17:<18} {'-'*9:>10} {'-'*8:>9} {'-'*8:>9} {'-'*8:>9} {'-'*8:>9}")
        for _, r in sig.iterrows():
            t = targets[r["symbol"]]
            print(f"  {r['rank']:<5} {r['symbol']:<18} {r['momentum_12m']*100:>9.1f}% {r['close']:>8.2f} {t['entry']:>9.2f} {t['hard_stop']:>9.2f} {t['trail_trigger']:>9.2f}")

        max_pos = MOM_MAX_POSITIONS
        entries_today = min(len(sig), max_pos)
        print(f"\n  Max positions: {max_pos}  |  Entering: {entries_today}")
        print(f"  Stop: {abs(MOM_STOP_LOSS)*100:.0f}%  |  Trail activate: +{MOM_TRAIL_ACTIVATE*100:.0f}%, trail distance: {abs(MOM_TRAIL_DISTANCE)*100:.0f}%")
        print(f"  Rebalance: Monthly (every 21 trading days)  |  Max {MOM_SECTOR_MAX} per sector")
        if crash_mode:
            print(f"  *** CRASH REGIME: Do NOT enter. Wait for 20d return > -3%. ***")

    else:
        print(f"  Computing characteristics...")
        char_data = precompute_all_characteristics(data, window=20)

        if scan_date not in next(iter(char_data.values()), pd.DataFrame()).index:
            available = sorted(set(d for s in char_data for d in char_data[s].index))
            closest = [d for d in available if d >= scan_date]
            if not closest:
                print(f"  No trading data on or after {scan_date.date()}")
                sys.exit(1)
            scan_date = closest[0]
            print(f"  Adjusted to nearest trading day: {scan_date.date()}")

        sig = generate_signals(data, char_data, scan_date)
        if sig.empty:
            print(f"\n  No signals on {scan_date.date()}.")
            _save_json(json_output, scan_date, strategy, sig, {}, regime, get_sector_map(universe_slug_or_path))
            sys.exit(1)

        targets = {}
        for _, r in sig.iterrows():
            raw_entry = r["close"]
            entry_price = raw_entry * ENTRY_COST_MULT
            targets[r["symbol"]] = {
                "entry": round(entry_price, 2),
                "target1": round(entry_price * (1 + PROFIT_TARGET_1) * EXIT_COST_MULT, 2),
                "target2": round(entry_price * (1 + PROFIT_TARGET_2) * EXIT_COST_MULT, 2),
                "hard_stop": round(entry_price * (1 + HARD_STOP) * EXIT_COST_MULT, 2),
                "trail_trigger": round(entry_price * (1 + TRAIL_ACTIVATE), 2),
                "trail_stop": round(entry_price * (1 + TRAIL_ACTIVATE) * (1 - TRAIL_DISTANCE) * EXIT_COST_MULT, 2),
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

    rebalance_day = "Friday" if pd.Timestamp.now().weekday() < 4 else "next Friday"
    print(f"\n  Entry Timing: Signal detected — next entry on {rebalance_day} (rebalance day)")
    print(f"  *Entry price includes slippage ({SLIPPAGE:.1%}) + brokerage ({BROKERAGE:.2%})")
    print(f"{'='*70}\n")
    if output:
        os.makedirs(os.path.dirname(output), exist_ok=True)
        html = generate_html(scan_date.strftime("%Y-%m-%d"), sig, regime, targets, universe_name, strategy)
        with open(output, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  HTML report saved: {output}")

    json_path = json_output or (output.replace(".html", ".json") if output and output.endswith(".html") else None)
    if json_path:
        _save_json(json_path, scan_date, strategy, sig, targets, regime, get_sector_map(universe_slug_or_path))


def main():
    parser = argparse.ArgumentParser(description="Daily scan for actionable signals")
    parser.add_argument("--universe", "-u", default="nifty50",
                        help="Universe slug or path to JSON (default: nifty50)")
    parser.add_argument("--date", default=None,
                        help="Override date (YYYY-MM-DD). Default: today")
    parser.add_argument("--output", default=None,
                        help="Save HTML report to file")
    parser.add_argument("--json-output", default=None,
                        help="Save JSON signal data to file (default: derived from --output)")
    parser.add_argument("--strategy", "-s", default="contrarian", choices=["contrarian", "momentum"],
                        help="Strategy to scan for (default: contrarian)")
    args = parser.parse_args()
    scan(args.universe, args.date, args.output, args.strategy, args.json_output)


if __name__ == "__main__":
    main()
