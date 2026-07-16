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

import numpy as np
import pandas as pd
import yfinance as yf

from src.backtest import generate_signals, generate_momentum_signals, compute_momentum_stops
from src.config import (
    HARD_STOP, PROFIT_TARGET_1, PROFIT_TARGET_2,
    SLIPPAGE, BROKERAGE, TRAIL_ACTIVATE, TRAIL_DISTANCE,
    MOM_MAX_POSITIONS, MOM_MIN_POSITIONS,
    MOM_STOP_LOSS, MOM_TRAIL_ACTIVATE, MOM_TRAIL_DISTANCE,
    MOM_MIN_VOLUME, MOM_SECTOR_MAX,
)
import json

from src.db import load_symbol_data, load_universe, get_sector_map
from src.features import precompute_all_characteristics
from src.factors import generate_factor_signals
from src.reporting import (
    _classify_regime, daily_scan_html, momentum_scan_html, factor_scan_html,
)

NIFTY_INDEX_TICKER = "^NSEI"

ENTRY_COST_MULT = 1 + SLIPPAGE + BROKERAGE
EXIT_COST_MULT = 1 - SLIPPAGE - BROKERAGE





def _save_json(json_path: str | None, scan_date, strategy, sig, targets, regime, sector_map):
    if not json_path:
        return
    out_dir = os.path.dirname(json_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
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
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  JSON data saved: {json_path}")


def scan(universe_slug_or_path: str, date_str: str | None = None, output: str | None = None, strategy: str = "contrarian", json_output: str | None = None, top: int = 0):
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
    _df = yf.download(NIFTY_INDEX_TICKER, period="6mo", progress=False, auto_adjust=True)
    if not _df.empty:
        _df.index = pd.to_datetime(_df.index).tz_localize(None)
        if isinstance(_df.columns, pd.MultiIndex):
            _df.columns = [c[0].lower() for c in _df.columns]
        else:
            _df.columns = [str(c).lower() for c in _df.columns]
        _close = _df["close"]; _price = _close.iloc[-1]
        _ret_20d = _close.iloc[-1] / _close.iloc[-min(21, len(_close))] - 1 if len(_close) >= 21 else 0
        _atr_pct = ((_df["high"] - _df["low"]).rolling(20).mean().iloc[-1]) / _price * 100 if _price > 0 else 0
        _reg = _classify_regime(_ret_20d * 100)
        regime = {"index_price": round(_price, 2), "trend_20d": round(_ret_20d * 100, 2),
                  "trend_label": _reg.get("trend_label", "Unknown"), "atr_pct": round(_atr_pct, 2),
                  "max_positions": _reg.get("max_positions", 1), "action": _reg.get("action", "Skip"),
                  "regime_note": _reg.get("regime_note", "")}
    else:
        regime = {"index_price": 0, "trend_20d": 0, "trend_label": "Unknown", "atr_pct": 0,
                  "max_positions": 1, "action": "Unknown", "regime_note": ""}
    crash_mode = regime["trend_20d"] < -8
    print(f"  {NIFTY_INDEX_TICKER} @ {regime['index_price']} | {regime['trend_label']} ({regime['trend_20d']:+.2f}% 20d) | ATR {regime['atr_pct']}%")
    print(f"  >>> RECOMMENDATION: {regime['action']} (max {regime['max_positions']} positions) — {regime['regime_note']}")
    if crash_mode and strategy == "momentum":
        print(f"  *** CRASH MODE: Momentum strategy deactivated. Hold cash. ***")

    print(f"  Loading data...")
    data = load_symbol_data(universe_slug_or_path)
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

    elif strategy == "factor":
        print(f"  Computing momentum and volatility for each stock...")

        available = sorted(set(d for s in data for d in data[s].index))
        if scan_date not in available:
            closest = [d for d in available if d >= scan_date]
            if not closest:
                print(f"  No trading data on or after {scan_date.date()}")
                sys.exit(1)
            scan_date = closest[0]
            print(f"  Adjusted to nearest trading day: {scan_date.date()}")

        sig = generate_factor_signals(data, scan_date)
        if sig.empty:
            print(f"\n  No factor signals on {scan_date.date()}.")
            _save_json(json_output, scan_date, strategy, sig, {}, regime, get_sector_map(universe_slug_or_path))
            sys.exit(1)

        # Sector diversification: take top 1 per sector, then top overall
        sector_map = get_sector_map(universe_slug_or_path)
        sig["sector"] = sig["symbol"].map(sector_map).fillna("Unknown")
        pool_size = max(top * 5, 15)
        top_pool = sig.head(pool_size)
        diversified = top_pool.groupby("sector").head(1).reset_index(drop=True)
        diversified = diversified.sort_values("conviction", ascending=False).head(top)
        diversified["rank"] = range(1, len(diversified) + 1)
        sig = diversified

        bear_skip = regime.get("trend_label", "") == "Bear"
        if bear_skip:
            print(f"  *** Bear regime: skip entry. Hold cash. ***")

        targets = {}
        for _, r in sig.iterrows():
            targets[r["symbol"]] = {
                "entry": round(r["close"], 2),
            }

        print(f"\n  Factor Signals: {len(sig)}")
        print(f"  {'Rank':<5} {'Symbol':<18} {'Conviction':>10} {'Price':>9}")
        print(f"  {'-'*4:<5} {'-'*17:<18} {'-'*9:>10} {'-'*8:>9}")
        for _, r in sig.iterrows():
            print(f"  {r['rank']:<5} {r['symbol']:<18} {r['conviction']:>10.4f} {r['close']:>8.2f}")

        max_pos = top
        entries_today = 0 if bear_skip else min(len(sig), max_pos)
        print(f"  Max positions: {top}  |  Entering: {entries_today}")
        print(f"  Hold: 10 trading days  |  Exit: next Friday")
        if bear_skip:
            print(f"  *** BEAR REGIME: Skip entry. Wait for 20d return > -3%. ***")

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
        out_dir = os.path.dirname(output)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        date_str = scan_date.strftime("%Y-%m-%d")
        if strategy == "momentum":
            html = momentum_scan_html(
                date_str, sig, regime, targets, universe_name,
                mom_stop_loss=MOM_STOP_LOSS, mom_trail_activate=MOM_TRAIL_ACTIVATE,
                mom_trail_distance=MOM_TRAIL_DISTANCE, max_positions=MOM_MAX_POSITIONS,
            )
        elif strategy == "factor":
            html = factor_scan_html(date_str, sig, regime, universe_name)
        else:
            html = daily_scan_html(
                date_str, sig, regime, targets, universe_name,
                profit_target_1=PROFIT_TARGET_1, profit_target_2=PROFIT_TARGET_2,
                hard_stop=HARD_STOP, trail_activate=TRAIL_ACTIVATE,
                trail_distance=TRAIL_DISTANCE, max_positions=regime.get("max_positions", 3),
            )
        with open(output, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  HTML report saved: {output}")

    json_path = json_output or (output.replace(".html", ".json") if output and output.endswith(".html") else None)
    if json_path:
        _save_json(json_path, scan_date, strategy, sig, targets, regime, get_sector_map(universe_slug_or_path))

    if strategy == "factor" and json_path:
        import json as _json
        _dir = os.path.dirname(os.path.abspath(json_path)) if json_path else "."
        _latest = os.path.join(_dir, "latest.json")
        with open(_latest, "w", encoding="utf-8") as f:
            _json.dump({"date": scan_date.strftime("%Y-%m-%d")}, f)
        print(f"  latest.json saved: {_latest}")


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
    parser.add_argument("--strategy", "-s", default="contrarian", choices=["contrarian", "momentum", "factor"],
                        help="Strategy to scan for (default: contrarian)")
    parser.add_argument("--top", type=int, default=5,
                        help="Only show top N ranked stocks (default: 5)")
    args = parser.parse_args()
    scan(args.universe, args.date, args.output, args.strategy, args.json_output, top=args.top)


if __name__ == "__main__":
    main()
