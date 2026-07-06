"""
Check forward returns of signals generated on a historical date.
Usage: python forward_check.py --date 2026-05-01
       python forward_check.py --date 2026-03-16 --universe RELIANCE.NS,TCS.NS,HDFCBANK.NS
       python forward_check.py --date 2026-01-15 --capital 5000000 --horizons 3 7 14
       python forward_check.py --date 2026-06-19 --output report.html
"""

import pandas as pd
import argparse
from data import fetch_nifty_50_data
from characteristics import precompute_all_characteristics
from signal_generator import generate_signals, HORIZON
from constituents import get_nifty_50_symbols


def resolve_universe(universe: str) -> list[str]:
    if universe.upper() == "NIFTY50":
        return get_nifty_50_symbols()
    return [s.strip() for s in universe.split(",") if s.strip()]


def find_trading_dates(data, date, ahead):
    all_dates = sorted(set(
        d for s in data for d in data[s].index
    ))
    available = [d for d in all_dates if d >= date]
    if not available:
        return []
    return available[:ahead + 1]


def build_horizon_results(data, sig, entry_date, horizons):
    horizon_data = {}
    for h in horizons:
        dates = find_trading_dates(data, entry_date, h)
        if len(dates) <= 1:
            horizon_data[h] = {"dates": dates, "results": [], "df": pd.DataFrame()}
            continue
        exit_date = dates[-1]
        results = []
        for _, row in sig.iterrows():
            symbol = row["symbol"]
            ep = row["close"]
            if symbol not in data or exit_date not in data[symbol].index:
                results.append({"symbol": symbol, "entry_date": entry_date, "exit_date": exit_date,
                                "entry_price": ep, "exit_price": None, "return_pct": None,
                                "min_intra_pct": None, "status": "no_data"})
                continue
            xp = data[symbol].loc[exit_date, "close"]
            ret = (xp / ep - 1) * 100
            min_ret = None
            for d in dates[1:]:
                if d in data[symbol].index:
                    r = (data[symbol].loc[d, "close"] / ep - 1) * 100
                    if min_ret is None or r < min_ret:
                        min_ret = r
            results.append({"symbol": symbol, "entry_date": entry_date, "exit_date": exit_date,
                            "entry_price": round(ep, 2), "exit_price": round(xp, 2),
                            "return_pct": round(ret, 2), "min_intra_pct": round(min_ret, 2) if min_ret is not None else None,
                            "status": "ok"})
        horizon_data[h] = {"dates": dates, "exit_date": exit_date, "results": results, "df": pd.DataFrame(results)}
    return horizon_data


def generate_html(entry_date, sig, horizon_data, horizons, universe, capital):
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    rows_html = ""
    for _, r in sig.iterrows():
        rows_html += f"""
        <tr>
            <td>{r['rank']}</td>
            <td>{r['symbol']}</td>
            <td>{r['close']:.2f}</td>
            <td>{r['conviction']:.4f}</td>
        </tr>"""

    horizon_sections = ""
    for h in horizons:
        hd = horizon_data.get(h, {})
        df = hd.get("df", pd.DataFrame())
        if df.empty:
            horizon_sections += f"<h2>{h} Trading Days</h2><p class='no-data'>Insufficient data</p>"
            continue
        exit_date = hd.get("exit_date")
        dates = hd.get("dates", [])
        n_days = len(dates) - 1 if len(dates) > 1 else 0
        cal_days = (exit_date - entry_date).days if exit_date else 0
        winners = df[df["return_pct"] > 0] if not df.empty else pd.DataFrame()
        losers = df[df["return_pct"] < 0] if not df.empty else pd.DataFrame()
        wr = f"{len(winners)}/{len(df)} ({len(winners)/len(df)*100:.0f}%)" if len(df) > 0 else "N/A"
        avg_ret = df["return_pct"].mean() if not df.empty and len(df) > 0 else 0
        best_row = df.loc[df["return_pct"].idxmax()] if not df.empty and len(df) > 0 and df["return_pct"].notna().any() else None
        worst_row = df.loc[df["return_pct"].idxmin()] if not df.empty and len(df) > 0 and df["return_pct"].notna().any() else None

        trs = ""
        for _, r in df.iterrows():
            cls = "win" if r["return_pct"] is not None and r["return_pct"] > 0 else "loss" if r["return_pct"] is not None and r["return_pct"] < 0 else ""
            ret_s = f"{r['return_pct']:+.2f}%" if r["return_pct"] is not None else "N/A"
            min_s = f"{r['min_intra_pct']:+.2f}%" if r["min_intra_pct"] is not None else "N/A"
            ep_s = f"{r['entry_price']:.2f}" if r["entry_price"] else "N/A"
            xp_s = f"{r['exit_price']:.2f}" if r["exit_price"] else "N/A"
            ed_s = entry_date.strftime("%Y-%m-%d")
            xd_s = r["exit_date"].strftime("%Y-%m-%d") if hasattr(r.get("exit_date"), "strftime") else str(r.get("exit_date", "N/A"))
            trs += f"<tr class='{cls}'><td>{r['symbol']}</td><td>{ed_s}</td><td>{ep_s}</td><td>{xd_s}</td><td>{xp_s}</td><td>{ret_s}</td><td>{min_s}</td></tr>"

        best_s = f"{best_row['symbol']} ({best_row['return_pct']:+.2f}%)" if best_row is not None else "N/A"
        worst_s = f"{worst_row['symbol']} ({worst_row['return_pct']:+.2f}%)" if worst_row is not None else "N/A"

        horizon_sections += f"""
        <div class="horizon-section">
            <h2>{h} Trading Days</h2>
            <p>Entry: {entry_date.strftime('%Y-%m-%d')} → Exit: {exit_date.strftime('%Y-%m-%d') if exit_date else 'N/A'} ({cal_days} cal days, {n_days} trading days)</p>
            <table>
                <tr><th>Symbol</th><th>Entry Date</th><th>Entry Price</th><th>Exit Date</th><th>Exit Price</th><th>Return</th><th>Min Intra</th></tr>
                {trs}
            </table>
            <div class="summary">
                <p><strong>Winners:</strong> {wr} &nbsp;|&nbsp; <strong>Avg Return:</strong> {avg_ret:+.2f}% &nbsp;|&nbsp; <strong>Best:</strong> {best_s} &nbsp;|&nbsp; <strong>Worst:</strong> {worst_s}</p>
            </div>
        </div>"""

    cross_rows = ""
    all_rets = {}
    for _, row in sig.iterrows():
        sym = row["symbol"]
        all_rets[sym] = {}
        for h in horizons:
            hd = horizon_data.get(h, {})
            for r in hd.get("results", []):
                if r["symbol"] == sym and r["return_pct"] is not None:
                    all_rets[sym][h] = r["return_pct"]
    for sym in all_rets:
        rets = all_rets[sym]
        vals = [v for v in rets.values() if v is not None]
        avg = sum(vals) / len(vals) if vals else 0
        cells = "".join(f"<td class='{'win' if rets.get(h,0)>0 else 'loss'}'>" + (f"{rets[h]:+.2f}%" if h in rets else "N/A") + "</td>" for h in horizons)
        avg_cls = "win" if avg > 0 else "loss"
        cross_rows += f"<tr><td>{sym}</td>{cells}<td class='{avg_cls}'>{avg:+.2f}%</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Forward Return Report — {entry_date.strftime('%Y-%m-%d')}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 30px; background: #f5f5f5; color: #333; }}
.container {{ max-width: 1100px; margin: auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
h1 {{ margin: 0 0 5px; color: #1a1a2e; }}
.subtitle {{ color: #666; font-size: 14px; margin-bottom: 20px; }}
.header-grid {{ display: flex; gap: 20px; margin-bottom: 24px; flex-wrap: wrap; }}
.header-item {{ background: #f8f9fa; padding: 12px 20px; border-radius: 6px; flex: 1; min-width: 120px; }}
.header-item label {{ display: block; font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }}
.header-item .value {{ font-size: 18px; font-weight: 600; color: #1a1a2e; }}
h2 {{ color: #1a1a2e; border-bottom: 2px solid #e9ecef; padding-bottom: 8px; margin-top: 30px; }}
table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e9ecef; }}
th {{ background: #f8f9fa; font-weight: 600; color: #555; }}
tr:hover {{ background: #f1f3f5; }}
.win {{ color: #2d7d2d; font-weight: 600; }}
.loss {{ color: #c0392b; font-weight: 600; }}
.summary {{ background: #f8f9fa; padding: 12px 16px; border-radius: 6px; margin: 8px 0; font-size: 14px; }}
.no-data {{ color: #999; font-style: italic; }}
.horizon-section {{ margin-bottom: 10px; }}
.footer {{ margin-top: 30px; padding-top: 16px; border-top: 1px solid #e9ecef; font-size: 12px; color: #999; }}
</style>
</head>
<body>
<div class="container">
    <h1>Forward Return Report</h1>
    <div class="subtitle">Generated {now}</div>
    <div class="header-grid">
        <div class="header-item"><label>Entry Date</label><div class="value">{entry_date.strftime('%Y-%m-%d')} ({entry_date.strftime('%A')})</div></div>
        <div class="header-item"><label>Universe</label><div class="value">{len(resolve_universe(universe))} stocks</div></div>
        <div class="header-item"><label>Capital</label><div class="value">INR {capital:,.0f}</div></div>
        <div class="header-item"><label>Signals</label><div class="value">{len(sig)}</div></div>
    </div>
    <h2>Signals</h2>
    <table><tr><th>Rank</th><th>Symbol</th><th>Entry Price</th><th>Conviction</th></tr>{rows_html}</table>
    {horizon_sections}
    <h2>Cross-Horizon Summary</h2>
    <table><tr><th>Symbol</th>{"".join(f'<th>{h}d</th>' for h in horizons)}<th>Avg</th></tr>{cross_rows}</table>
    <div class="footer">Volatility Contrarian Strategy — Forward Return Check</div>
</div>
</body>
</html>"""
    return html


def check_forward(date_str, horizons=(5, 10, 20), universe="NIFTY50", capital=10_000_000, output=None):
    symbols = resolve_universe(universe)
    entry_date = pd.Timestamp(date_str)
    print(f"\n{'='*70}")
    print(f"  FORWARD RETURN CHECK")
    print(f"  Entry date: {entry_date.date()} ({entry_date.strftime('%A')})")
    print(f"  Universe:   {len(symbols)} stocks" + (f" ({universe})" if universe != "NIFTY50" else " (NIFTY50)"))
    print(f"  Capital:    INR {capital:,.0f}")
    print(f"{'='*70}")

    data = fetch_nifty_50_data(years=3)
    data = {s: data[s] for s in data if s in symbols}
    char_data = precompute_all_characteristics(data, window=HORIZON)

    if entry_date not in char_data.get(list(char_data.keys())[0], pd.DataFrame()).index:
        available = sorted(set(d for s in char_data for d in char_data[s].index))
        closest = [d for d in available if d >= entry_date]
        if not closest:
            print(f"  No trading data found on or after {entry_date.date()}")
            return
        entry_date = closest[0]
        print(f"  Adjusted to nearest trading day: {entry_date.date()}")

    sig = generate_signals(data, char_data, entry_date)

    if sig.empty:
        print(f"\n  No signals generated on {entry_date.date()}.")
        return

    print(f"\n  Signals generated: {len(sig)}")
    print(f"  {'Rank':<5} {'Symbol':<18} {'Close':>8} {'Conviction':>10}")
    print(f"  {'-'*4:<5} {'-'*17:<18} {'-'*7:>8} {'-'*9:>10}")
    for _, row in sig.iterrows():
        print(f"  {row['rank']:<5} {row['symbol']:<18} {row['close']:>8.2f} {row['conviction']:>10.4f}")

    horizon_data = build_horizon_results(data, sig, entry_date, horizons)

    for h in horizons:
        hd = horizon_data.get(h, {})
        df = hd.get("df", pd.DataFrame())
        dates = hd.get("dates", [])
        if len(dates) <= 1:
            print(f"\n  [HORIZON {h}d] Not enough data ahead")
            continue
        exit_date = hd["exit_date"]
        actual_days = (exit_date - entry_date).days
        n_trading = len(dates) - 1
        print(f"\n{'─'*70}")
        print(f"  {h} TRADING DAYS — Entry {entry_date.date()} → Exit {exit_date.date()} ({actual_days} cal days, {n_trading} trading days)")
        print(f"{'─'*70}")
        print(f"  {'Symbol':<18} {'Entry':>9} {'Exit':>9} {'Return':>8} {'Min Intra':>9} {'Status':<10}")
        print(f"  {'-'*17:<18} {'-'*8:>9} {'-'*8:>9} {'-'*7:>8} {'-'*8:>9} {'-'*9:<10}")
        winners = 0
        for r in hd["results"]:
            if r["return_pct"] is None:
                continue
            ret = r["return_pct"]
            min_s = f"{r['min_intra_pct']:+.2f}%" if r["min_intra_pct"] is not None else "N/A"
            status = "✅ WIN" if ret > 0 else "❌ LOSS"
            if ret > 0:
                winners += 1
            print(f"  {r['symbol']:<18} {r['entry_price']:>9.2f} {r['exit_price']:>9.2f} {ret:>+8.2f}% {min_s:>9} {status:<10}")
        avg_ret = df["return_pct"].mean()
        print(f"\n  Summary: {winners}/{len(hd['results'])} wins ({winners/len(hd['results'])*100:.0f}%) | Avg: {avg_ret:+.2f}%")

    all_rets = {}
    for _, row in sig.iterrows():
        sym = row["symbol"]
        all_rets[sym] = {}
        for h in horizons:
            for r in horizon_data.get(h, {}).get("results", []):
                if r["symbol"] == sym and r["return_pct"] is not None:
                    all_rets[sym][h] = r["return_pct"]

    print(f"\n{'='*70}")
    print(f"  CROSS-HORIZON SUMMARY")
    print(f"{'='*70}")
    header = f"  {'Symbol':<18}"
    for h in horizons:
        header += f" {f'{h}d':>8}"
    header += f" {'Avg':>8}"
    print(header)
    print(f"  {'-'*17:<18}" + " " + " ".join(f"{'-'*6:>8}" for _ in horizons) + f" {'-'*6:>8}")
    for sym in all_rets:
        rets = all_rets[sym]
        vals = [v for v in rets.values() if v is not None]
        avg = sum(vals) / len(vals) if vals else 0
        line = f"  {sym:<18}"
        for h in horizons:
            line += f" {rets.get(h, 0):>+7.2f}%" if h in rets else f" {'N/A':>8}"
        line += f" {avg:>+7.2f}%"
        print(line)
    print(f"\n  Entry Date: {entry_date.date()}  |  Signals: {len(sig)}")

    if output:
        html = generate_html(entry_date, sig, horizon_data, horizons, universe, capital)
        with open(output, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\n  HTML report saved: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check forward returns of signals on a historical date")
    parser.add_argument("--date", required=True, help="Historical date (YYYY-MM-DD)")
    parser.add_argument("--horizons", nargs="+", type=int, default=[5, 10, 20],
                        help="Forward horizons in trading days (default: 5 10 20)")
    parser.add_argument("--universe", default="NIFTY50",
                        help="Universe: 'NIFTY50' or comma-separated symbols like 'RELIANCE.NS,TCS.NS'")
    parser.add_argument("--capital", type=float, default=10_000_000,
                        help="Starting capital for context (default: 10,000,000)")
    parser.add_argument("--output", default=None,
                        help="Save HTML report to file (e.g. report.html)")
    args = parser.parse_args()
    check_forward(args.date, args.horizons, args.universe, args.capital, args.output)
