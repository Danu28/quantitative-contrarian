"""
Cross-Sectional Momentum — No-Churn Approach
Buy top decile by 1yr momentum, hold fixed period, NO intermediate rebalancing.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.db import load_data, load_universe
from src.config import CAPITAL, SLIPPAGE, BROKERAGE
import yfinance as yf


def load_nifty(years=8):
    try:
        df = yf.download("^NSEI", period=f"{years}y", progress=False, auto_adjust=True)
        if df.empty: return pd.Series(dtype=float)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [str(c).lower() for c in df.columns]
        return df["close"]
    except:
        return pd.Series(dtype=float)


def run_nochurn_backtest(
    universe="nifty500", years=5, capital=CAPITAL,
    lookback=252, top_pct=0.10, time_stop=63, hard_stop=-0.08,
):
    print(f"\n{'='*78}")
    print(f"  MOMENTUM — NO CHURN")
    print(f"  Universe: {universe} | {years}y | LB={lookback}d | Top {top_pct:.0%}")
    print(f"  Hold fixed {time_stop}d | HS={hard_stop:.0%} | NO weekly rebalance")
    print(f"{'='*78}")

    # Load data
    df_all = load_data(universe, auto_fetch=False)
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=years)
    df_all = df_all[df_all["date"] >= cutoff]
    config = load_universe(universe)

    data = {}
    for sym in config["symbols"]:
        sub = df_all[df_all["symbol"] == sym].copy()
        if sub.empty: continue
        sub = sub.set_index("date")
        sub.index = pd.DatetimeIndex(sub.index)
        data[sym] = sub

    all_dates = sorted(set(d for s in data for d in data[s].index))
    print(f"  Loaded {len(data)} stocks | {len(all_dates)} days")
    print(f"  Range: {all_dates[0].date()} to {all_dates[-1].date()}")

    cost = SLIPPAGE + BROKERAGE

    # ========== STRATEGY ==========
    # Every N days, pick top decile by 1yr momentum, hold for time_stop days.
    # NO in-between selling. Only exit on hard stop or time stop.

    entry_interval = 21  # new cohort every ~month
    cohorts = []  # list of {entry_date, symbols: {sym: shares}, cost_basis}

    cash = capital
    equity_curve = []
    trades = []
    peak = capital

    for date in all_dates:
        prices = {s: data[s].loc[date, "close"] for s in data if date in data[s].index}

        # Check exits for all cohorts
        for c in cohorts[:]:
            days_held = (date - c["entry_date"]).days
            # Approximate trading days
            c["td"] = c.get("td", 0) + 1

            for sym in list(c["symbols"].keys()):
                if sym not in prices:
                    continue
                ret = prices[sym] / c["symbols"][sym]["ep"] - 1
                close_out = False
                reason = None

                if ret <= hard_stop:
                    close_out, reason = True, "hard_stop"
                elif c["td"] >= time_stop:
                    close_out, reason = True, "time_stop"

                if close_out:
                    shares = c["symbols"][sym]["shares"]
                    exit_val = shares * prices[sym] * (1 - cost)
                    cash += exit_val
                    trades.append({
                        "symbol": sym, "entry_date": c["entry_date"], "exit_date": date,
                        "entry_price": c["symbols"][sym]["ep"],
                        "exit_price": prices[sym],
                        "pnl_pct": ret * 100, "reason": reason,
                        "days_held": days_held,
                    })
                    del c["symbols"][sym]

            # Remove empty cohorts
            if not c["symbols"]:
                cohorts.remove(c)

        # On entry days, form new cohort
        date_idx = all_dates.index(date) if date in all_dates else -1
        if date_idx >= lookback and (len(cohorts) == 0 or (date - cohorts[-1]["entry_date"]).days >= entry_interval):
            past_date = all_dates[date_idx - lookback]

            # Rank by momentum
            records = []
            for sym, df in data.items():
                if date in df.index and past_date in df.index:
                    past_ret = df.loc[date, "close"] / df.loc[past_date, "close"] - 1
                    records.append((sym, past_ret))

            if records:
                records.sort(key=lambda x: x[1], reverse=True)
                n_select = max(1, int(len(records) * top_pct))
                selected = records[:n_select]

                if cash > 0:
                    # Each cohort gets 1/4 of capital to avoid overlap over-allocation
                    # (3 overlapping cohorts * 0.25 = 75% max deployment)
                    cohort_budget = min(cash, capital * 0.25)
                    alloc_per_stock = cohort_budget / n_select
                    cohort_symbols = {}
                    for sym, mom in selected:
                        if sym not in prices:
                            continue
                        ep = prices[sym] * (1 + cost)
                        shares = int(alloc_per_stock / ep)
                        if shares > 0 and cash >= shares * ep:
                            cash -= shares * ep
                            cohort_symbols[sym] = {"ep": ep, "shares": shares}

                    if cohort_symbols:
                        cohorts.append({
                            "entry_date": date,
                            "symbols": cohort_symbols,
                            "td": 0,
                        })
                        deployed = capital - cash + sum(
                            sd["shares"] * prices.get(s, 0)
                            for c in cohorts for s, sd in c["symbols"].items()
                        )
                        print(f"  Cohort {date.date()}: {len(cohort_symbols)} stocks, ${cohort_budget:,.0f} budget, ${deployed:,.0f} total deployed")

        # Equity tracking
        pv = 0
        for c in cohorts:
            for sym, sd in c["symbols"].items():
                if sym in prices:
                    pv += sd["shares"] * prices[sym]
        total = cash + pv
        peak = max(peak, total)
        equity_curve.append({"date": date, "equity": total, "pv": pv, "npos": sum(len(c["symbols"]) for c in cohorts)})

    # ========== RESULTS ==========
    eq = pd.DataFrame(equity_curve).set_index("date")
    tdf = pd.DataFrame(trades) if trades else pd.DataFrame()

    if len(eq) < 20:
        print("  ERROR: insufficient data")
        return

    tr = eq["equity"].iloc[-1] / eq["equity"].iloc[0] - 1
    days = (eq.index[-1] - eq.index[0]).days
    cagr = (1 + tr) ** (365 / max(days, 1)) - 1
    rets = eq["equity"].pct_change().dropna()
    vol = rets.std() * np.sqrt(252)
    rf = 0.065
    sharpe = (rets.mean() * 252 - rf) / vol if vol > 0 else 0
    downside = rets[rets < 0].std() * np.sqrt(252)
    sortino = (rets.mean() * 252 - rf) / downside if downside > 0 and (rets < 0).sum() > 1 else 0
    mdd = ((eq["equity"] - eq["equity"].cummax()) / eq["equity"].cummax()).min()
    calmar = cagr / abs(mdd) if mdd < 0 else 0

    wr = (tdf["pnl_pct"] > 0).mean() if not tdf.empty else 0
    ps = tdf[tdf["pnl_pct"] > 0]["pnl_pct"].sum() if not tdf.empty else 0
    ns = abs(tdf[tdf["pnl_pct"] < 0]["pnl_pct"].sum()) if not tdf.empty else 0
    pf = ps / ns if ns > 0 else float("inf")
    expectancy = tdf["pnl_pct"].mean() if not tdf.empty else 0
    exposure = (eq["pv"] / eq["equity"]).mean() * 100
    turnover = len(tdf) / max(1, days / 365)

    nifty = load_nifty(years=years+2)
    bench_cagr = 0
    if not nifty.empty and len(nifty) > 10:
        b = nifty[nifty.index >= eq.index[0]]
        if len(b) > 10:
            br = b.iloc[-1] / b.iloc[0] - 1
            bd = (b.index[-1] - b.index[0]).days
            bench_cagr = (1 + br) ** (365 / max(bd, 1)) - 1

    print(f"\n  {'='*78}")
    print(f"  RESULTS")
    print(f"  {'='*78}")
    print(f"  Period: {eq.index[0].date()} to {eq.index[-1].date()} ({len(eq)} days)")
    print(f"  Cohorts: {len(cohorts) + 1 if any(c['symbols'] for c in cohorts) else len([c for c in cohorts if not c['symbols']])}")
    print(f"\n  Return:")
    print(f"    Total:         {tr*100:>+8.2f}%")
    print(f"    CAGR:          {cagr*100:>+8.2f}%")
    print(f"    Benchmark:     {bench_cagr*100:>+8.2f}%")
    print(f"    Excess:        {(cagr-bench_cagr)*100:>+8.2f}%")
    print(f"  Risk:")
    print(f"    Vol:           {vol*100:>8.2f}%")
    print(f"    MaxDD:         {mdd*100:>8.2f}%")
    print(f"  Risk-Adj:")
    print(f"    Sharpe:        {sharpe:>8.2f}")
    print(f"    Sortino:       {sortino:>8.2f}")
    print(f"    Calmar:        {calmar:>8.2f}")
    print(f"  Trades:")
    print(f"    Total:         {len(tdf):>8}")
    print(f"    WR:            {wr*100:>7.1f}%")
    print(f"    PF:            {pf:>8.2f}")
    print(f"    Expectancy:    {expectancy:>+8.2f}%")
    print(f"    Turnover/yr:   {turnover:>8.1f}")
    print(f"  Portfolio:")
    print(f"    Exposure:      {exposure:>7.1f}%")
    print(f"    Avg Positions: {eq['npos'].mean():>7.1f}")

    if not tdf.empty:
        print(f"\n  Exit Reasons:")
        for reason, g in tdf.groupby("reason"):
            avg = g["pnl_pct"].mean()
            wins = (g["pnl_pct"] > 0).sum()
            print(f"    {reason:<20} {len(g):4d}  Avg: {avg:+.2f}%  Win: {wins}/{len(g)}")

    # Win/loss magnitude
    wl_ratio_val = 0
    if not tdf.empty:
        winners = tdf[tdf["pnl_pct"] > 0]
        losers = tdf[tdf["pnl_pct"] < 0]
        if len(winners) > 0 and len(losers) > 0:
            wl_ratio_val = winners["pnl_pct"].mean() / abs(losers["pnl_pct"].mean())
            print(f"\n  Avg Win / Avg Loss: {winners['pnl_pct'].mean():.2f}% / {losers['pnl_pct'].mean():.2f}% = {wl_ratio_val:.2f}x")

    gates = [
        ("Sharpe > 0.5",        sharpe > 0.5),
        ("MaxDD < 20%",         abs(mdd) < 0.20),
        ("CAGR > 0",            cagr > 0),
        ("Trades >= 30",        len(tdf) >= 30),
        ("WR > 40%",            wr > 0.40),
        ("PF > 1.2",            pf > 1.2),
        ("Avg Win / Loss > 1.5", wl_ratio_val > 1.5),
    ]

    passed = sum(1 for _, p in gates if p)
    print(f"\n  Gates: {passed}/{len(gates)} passed")
    for n, p in gates:
        print(f"    [{'PASS' if p else 'FAIL'}] {n}")

    return {"cagr": cagr, "sharpe": sharpe, "mdd": mdd, "wr": wr, "pf": pf, "trades": len(tdf), "cohorts": len([c for c in cohorts if not c['symbols']])}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", default="nifty500")
    parser.add_argument("--years", type=int, default=6)
    parser.add_argument("--top-pct", type=float, default=0.10)
    parser.add_argument("--lookback", type=int, default=252)
    parser.add_argument("--time-stop", type=int, default=63)
    parser.add_argument("--hard-stop", type=float, default=-0.08)
    args = parser.parse_args()

    run_nochurn_backtest(
        universe=args.universe, years=args.years,
        lookback=args.lookback, top_pct=args.top_pct,
        time_stop=args.time_stop, hard_stop=args.hard_stop,
    )
