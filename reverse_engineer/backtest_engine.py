"""
Comprehensive backtest engine for Volatility Contrarian strategy.
Usage: python backtest_engine.py
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from data import fetch_nifty_50_data
from characteristics import precompute_all_characteristics
from portfolio import Portfolio, SLIPPAGE, BROKERAGE
from signal_generator import generate_signals
from constituents import get_nifty_50_symbols


def resolve_universe(universe: str) -> list[str]:
    if universe.upper() == "NIFTY50":
        return get_nifty_50_symbols()
    return [s.strip() for s in universe.split(",") if s.strip()]


@dataclass
class BacktestConfig:
    capital: float = 10_000_000
    universe: str = "NIFTY50"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    horizons: list = field(default_factory=lambda: [5, 10, 21])
    slippage: float = SLIPPAGE
    brokerage: float = BROKERAGE
    years: int = 3


@dataclass
class HorizonResult:
    horizon: int
    trades: pd.DataFrame
    equity: pd.DataFrame
    metrics: dict
    exposure: pd.Series
    monthly_returns: pd.DataFrame


def compute_metrics(eq: pd.DataFrame, trades: pd.DataFrame, capital: float) -> dict:
    if len(eq) < 5 or trades.empty:
        return {"status": "insufficient_data", "total_trades": len(trades)}

    total_ret = eq["equity"].iloc[-1] / eq["equity"].iloc[0] - 1
    days = (eq.index[-1] - eq.index[0]).days
    cagr = (1 + total_ret) ** (365 / max(days, 1)) - 1
    returns = eq["equity"].pct_change().dropna()
    vol = returns.std() * np.sqrt(252)
    rf = 0.065
    sharpe = (returns.mean() * 252 - rf) / vol if vol > 0 else 0
    downside = returns[returns < 0].std() * np.sqrt(252)
    sortino = (returns.mean() * 252 - rf) / downside if downside > 0 and (returns < 0).sum() > 1 else 0
    cummax = eq["equity"].cummax()
    dd = (eq["equity"] - cummax) / cummax
    mdd = dd.min()
    calmar = cagr / abs(mdd) if mdd < 0 else 0
    recovery = abs(total_ret / mdd) if mdd < 0 else 0
    avg_dd = dd[dd < 0].mean() if (dd < 0).any() else 0
    win_rate = (trades["pnl_pct"] > 0).sum() / len(trades) * 100
    pos_sum = trades[trades["pnl_pct"] > 0]["pnl_pct"].sum()
    neg_sum = abs(trades[trades["pnl_pct"] < 0]["pnl_pct"].sum())
    profit_factor = pos_sum / neg_sum if neg_sum > 0 else float("inf")
    expectancy = trades["pnl_pct"].mean()
    avg_gain = trades[trades["pnl_pct"] > 0]["pnl_pct"].mean() if (trades["pnl_pct"] > 0).any() else 0
    avg_loss = trades[trades["pnl_pct"] < 0]["pnl_pct"].mean() if (trades["pnl_pct"] < 0).any() else 0
    largest_win = trades["pnl_pct"].max() if not trades.empty else 0
    largest_loss = trades["pnl_pct"].min() if not trades.empty else 0
    avg_hold = trades["days_held"].mean()
    exposure = (eq["positions_value"] / eq["equity"]).mean() * 100
    turnover = trades["pnl_pct"].count() / max(1, days / 365)

    return {
        "total_return_pct": total_ret * 100,
        "cagr_pct": cagr * 100,
        "volatility_pct": vol * 100,
        "downside_dev_pct": downside * 100,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "recovery_factor": recovery,
        "max_drawdown_pct": mdd * 100,
        "avg_drawdown_pct": avg_dd * 100,
        "total_trades": len(trades),
        "win_rate_pct": win_rate,
        "loss_rate_pct": 100 - win_rate,
        "profit_factor": profit_factor,
        "expectancy_pct": expectancy,
        "avg_gain_pct": avg_gain,
        "avg_loss_pct": avg_loss,
        "largest_win_pct": largest_win,
        "largest_loss_pct": largest_loss,
        "avg_hold_days": avg_hold,
        "avg_exposure_pct": exposure,
        "turnover_per_year": turnover,
        "final_equity": eq["equity"].iloc[-1],
        "peak_equity": eq["equity"].max(),
    }


def run_horizon(
    data: dict,
    char_data: dict,
    horizon: int,
    config: BacktestConfig,
) -> HorizonResult:
    all_dates = sorted(set(d for s in char_data for d in char_data[s].index))
    if config.start_date:
        all_dates = [d for d in all_dates if d >= pd.Timestamp(config.start_date)]
    if config.end_date:
        all_dates = [d for d in all_dates if d <= pd.Timestamp(config.end_date)]
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=365 * config.years)
    all_dates = [d for d in all_dates if d >= cutoff]
    if not all_dates:
        return HorizonResult(horizon=horizon, trades=pd.DataFrame(), equity=pd.DataFrame(), metrics={"status": "no_data"}, exposure=pd.Series(), monthly_returns=pd.DataFrame())

    pf = Portfolio(capital=config.capital)
    for date in all_dates:
        prices = {s: data[s].loc[date, "close"] for s in data if date in data[s].index}
        sig = generate_signals(data, char_data, date)
        pf.process_day(sig, prices, date)

    eq = pd.DataFrame(pf.equity_curve).set_index("date") if pf.equity_curve else pd.DataFrame()
    trades = pf.get_trades_summary()
    exposure = eq["positions_value"] / eq["equity"] * 100 if not eq.empty else pd.Series()
    metrics = compute_metrics(eq, trades, config.capital)

    monthly = None
    if not eq.empty:
        monthly = eq["equity"].resample("ME").last().pct_change().dropna().to_frame(name="return")
        monthly.index = monthly.index.strftime("%Y-%m")

    return HorizonResult(
        horizon=horizon,
        trades=trades,
        equity=eq,
        metrics=metrics,
        exposure=exposure,
        monthly_returns=monthly,
    )


def print_report(results: list[HorizonResult], config: BacktestConfig):
    sep = "=" * 78

    print(f"\n{sep}")
    print("  VOLATILITY CONTRARIAN — COMPREHENSIVE BACKTEST REPORT")
    print(f"  Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Universe:  {config.universe} | Capital: INR {config.capital:,.0f}")
    print(f"  Slippage:  {config.slippage:.1%} | Brokerage: {config.brokerage:.1%}")
    print(f"{sep}")

    # Executive Summary
    print(f"\n{'─' * 78}")
    print("  1. EXECUTIVE SUMMARY")
    print(f"{'─' * 78}")
    best = max(results, key=lambda r: r.metrics.get("cagr_pct", -999))
    worst = min(results, key=lambda r: r.metrics.get("cagr_pct", -999))
    print(f"  Best horizon:     {best.horizon}d (CAGR {best.metrics.get('cagr_pct', 0):.2f}%)")
    print(f"  Worst horizon:    {worst.horizon}d (CAGR {worst.metrics.get('cagr_pct', 0):.2f}%)")
    all_cagr = [r.metrics.get("cagr_pct", 0) for r in results]
    all_trades = [r.metrics.get("total_trades", 0) for r in results]
    print(f"  CAGR range:       {min(all_cagr):.2f}% to {max(all_cagr):.2f}%")
    print(f"  Trade count:      {min(all_trades)} to {max(all_trades)}")
    print(f"  Risk-free rate:   6.5% (Indian 10-yr benchmark)")
    cagr_above_rf = any(c > 6.5 for c in all_cagr)
    print(f"  Any horizon beats RFR? {'Yes' if cagr_above_rf else 'No'}")

    for hr in results:
        h = hr.horizon
        m = hr.metrics
        eq = hr.equity
        trades = hr.trades

        print(f"\n{'─' * 78}")
        print(f"  2. HORIZON {h} TRADING DAYS — RESULTS")
        print(f"{'─' * 78}")

        if m.get("status") in ("insufficient_data", "no_data"):
            print(f"  ⚠️  Insufficient data for horizon {h}")
            continue

        first_date = eq.index[0].date() if not eq.empty else "N/A"
        last_date = eq.index[-1].date() if not eq.empty else "N/A"
        print(f"  Period:         {first_date} → {last_date}  ({len(eq)} trading days)")

        print(f"\n  ┌─── Return Metrics ─────────────────────────────────────────────┐")
        print(f"  │ Total Return          {m['total_return_pct']:>9.2f}%{'':>30}│")
        print(f"  │ CAGR                  {m['cagr_pct']:>9.2f}%{'':>30}│")
        print(f"  └──────────────────────────────────────────────────────────────────┘")

        print(f"\n  ┌─── Risk Metrics ───────────────────────────────────────────────┐")
        print(f"  │ Volatility            {m['volatility_pct']:>9.2f}%{'':>30}│")
        print(f"  │ Downside Deviation     {m['downside_dev_pct']:>9.2f}%{'':>30}│")
        print(f"  │ Max Drawdown          {m['max_drawdown_pct']:>9.2f}%{'':>30}│")
        print(f"  │ Avg Drawdown          {m['avg_drawdown_pct']:>9.2f}%{'':>30}│")
        print(f"  └──────────────────────────────────────────────────────────────────┘")

        print(f"\n  ┌─── Risk-Adjusted Metrics ───────────────────────────────────────┐")
        print(f"  │ Sharpe Ratio          {m['sharpe']:>9.2f}{'':>30}│")
        print(f"  │ Sortino Ratio         {m['sortino']:>9.2f}{'':>30}│")
        print(f"  │ Calmar Ratio          {m['calmar']:>9.2f}{'':>30}│")
        print(f"  │ Recovery Factor       {m['recovery_factor']:>9.2f}{'':>30}│")
        print(f"  └──────────────────────────────────────────────────────────────────┘")

        print(f"\n  ┌─── Trade Metrics ───────────────────────────────────────────────┐")
        print(f"  │ Total Trades          {m['total_trades']:>9}{'':>30}│")
        print(f"  │ Win Rate              {m['win_rate_pct']:>9.1f}%{'':>30}│")
        print(f"  │ Loss Rate             {m['loss_rate_pct']:>9.1f}%{'':>30}│")
        print(f"  │ Profit Factor         {m['profit_factor']:>9.2f}{'':>30}│")
        print(f"  │ Expectancy            {m['expectancy_pct']:>9.2f}%{'':>30}│")
        print(f"  │ Avg Gain              {m['avg_gain_pct']:>9.2f}%{'':>30}│")
        print(f"  │ Avg Loss              {m['avg_loss_pct']:>9.2f}%{'':>30}│")
        print(f"  │ Largest Win           {m['largest_win_pct']:>9.2f}%{'':>30}│")
        print(f"  │ Largest Loss          {m['largest_loss_pct']:>9.2f}%{'':>30}│")
        print(f"  │ Avg Hold Days         {m['avg_hold_days']:>9.1f}{'':>30}│")
        print(f"  └──────────────────────────────────────────────────────────────────┘")

        print(f"\n  ┌─── Portfolio Metrics ───────────────────────────────────────────┐")
        print(f"  │ Avg Exposure          {m['avg_exposure_pct']:>9.1f}%{'':>30}│")
        print(f"  │ Turnover/Yr           {m['turnover_per_year']:>9.1f}{'':>30}│")
        print(f"  │ Final Equity          INR {m['final_equity']:>11,.0f}{'':>16}│")
        print(f"  │ Peak Equity           INR {m['peak_equity']:>11,.0f}{'':>16}│")
        print(f"  └──────────────────────────────────────────────────────────────────┘")

        # Exit reason breakdown
        if not trades.empty:
            print(f"\n  Exit Reason Breakdown:")
            for reason, g in trades.groupby("exit_reason"):
                avg = g["pnl_pct"].mean()
                wins = (g["pnl_pct"] > 0).sum()
                total = len(g)
                print(f"    {reason:<20}  {total:4d} trades  Avg: {avg:+.2f}%  Win: {wins}/{total}")

        # Yearly breakdown
        if not eq.empty:
            print(f"\n  Yearly Returns:")
            eq_year = eq.copy()
            eq_year["year"] = eq_year.index.year
            for year, ye in eq_year.groupby("year"):
                yr = (ye["equity"].iloc[-1] / ye["equity"].iloc[0] - 1) * 100
                md = (ye["equity"].cummax() / ye["equity"] - 1).max() * 100
                yt = trades[trades["exit_date"].dt.year == year] if not trades.empty else pd.DataFrame()
                n_trades = len(yt)
                wr = (yt[yt["pnl_pct"] > 0].shape[0] / n_trades * 100) if n_trades > 0 else 0
                print(f"    {year}: Return {yr:+.2f}%  MaxDD {md:.2f}%  Trades {n_trades}  Win {wr:.0f}%")

        # Worst drawdown period
        if not eq.empty:
            dd_series = (eq["equity"] / eq["equity"].cummax() - 1) * 100
            worst_dd_idx = dd_series.idxmin()
            before_peak = eq["equity"].iloc[: eq.index.get_loc(worst_dd_idx) + 1].idxmax()
            print(f"\n  Worst Drawdown: {dd_series.min():.2f}%")
            print(f"    Peak:   {before_peak.date()}")
            print(f"    Trough: {worst_dd_idx.date()}")

        # Monthly returns table
        if hr.monthly_returns is not None and not hr.monthly_returns.empty:
            print(f"\n  Monthly Returns (%):")
            mr = hr.monthly_returns.copy()
            mr.columns = [f"{h}d"]
            mr.index.name = None
            pos_months = (mr.iloc[:, 0] > 0).sum()
            neg_months = (mr.iloc[:, 0] < 0).sum()
            print(f"    Positive months: {pos_months}/{len(mr)} ({pos_months/len(mr)*100:.0f}%)")
            print(f"    Negative months: {neg_months}/{len(mr)} ({neg_months/len(mr)*100:.0f}%)")
            worst_m = mr.iloc[:, 0].min()
            best_m = mr.iloc[:, 0].max()
            print(f"    Best month:  {best_m:+.2f}%")
            print(f"    Worst month: {worst_m:+.2f}%")

    # Cross-horizon comparison
    print(f"\n{'─' * 78}")
    print("  3. CROSS-HORIZON COMPARISON")
    print(f"{'─' * 78}")
    print(f"  {'Horizon':<10} {'CAGR':>8} {'MaxDD':>8} {'Sharpe':>8} {'WinRate':>8} {'PfFactor':>8} {'Trades':>8} {'AvgExp':>8}")
    print(f"  {'-'*8:>10} {'-'*8:>8} {'-'*8:>8} {'-'*8:>8} {'-'*8:>8} {'-'*8:>8} {'-'*8:>8} {'-'*8:>8}")
    for hr in sorted(results, key=lambda r: r.horizon):
        m = hr.metrics
        print(f"  {hr.horizon:>4}d      {m.get('cagr_pct', 0):>7.2f}% {m.get('max_drawdown_pct', 0):>7.2f}% {m.get('sharpe', 0):>7.2f} {m.get('win_rate_pct', 0):>6.1f}% {m.get('profit_factor', 0):>7.2f} {m.get('total_trades', 0):>7} {m.get('avg_exposure_pct', 0):>6.1f}%")

    # Stress test note
    print(f"\n{'─' * 78}")
    print("  4. STRESS TEST NOTES")
    print(f"{'─' * 78}")
    print(f"  Base costs:       Slippage {config.slippage:.1%} + Brokerage {config.brokerage:.1%}")
    print(f"  Double-cost test: Slippage {config.slippage*2:.1%} + Brokerage {config.brokerage*2:.1%}")
    for hr in results:
        m = hr.metrics
        if m.get("status") in ("insufficient_data", "no_data"):
            continue
        # Estimate impact of doubled costs
        avg_trade_roundtrip_cost = (config.slippage + config.brokerage) * 2 * 100
        doubled_cost = (config.slippage * 2 + config.brokerage * 2) * 2 * 100
        cost_impact = doubled_cost - avg_trade_roundtrip_cost
        adj_cagr = m.get("cagr_pct", 0) - cost_impact * m.get("turnover_per_year", 0) / 100
        print(f"  {hr.horizon}d:  Adj CAGR @2x costs: {adj_cagr:.2f}%  (base: {m.get('cagr_pct', 0):.2f}%)")

    # Deployment recommendation
    print(f"\n{'─' * 78}")
    print("  5. DEPLOYMENT RECOMMENDATION")
    print(f"{'─' * 78}")
    gates = check_gates(results)
    for gate, passed in gates.items():
        print(f"  {'✓' if passed else '✗'} {gate}")
    all_pass = all(gates.values())
    print(f"\n  OVERALL: {'✅ PASSED' if all_pass else '❌ FAILED'}")
    if all_pass:
        max_dd = max(r.metrics.get("max_drawdown_pct", 0) for r in results)
        if max_dd > -15:
            print("  Recommendation: Ready for Limited Live Deployment (low-risk diversifier)")
        else:
            print("  Recommendation: Ready for Paper Trading")
    else:
        print("  Recommendation: Requires Additional Research")

    print(f"\n{sep}\n")


def check_gates(results: list[HorizonResult]) -> dict:
    gates = {}
    for hr in results:
        m = hr.metrics
        if m.get("status") in ("insufficient_data", "no_data"):
            continue
        gates[f"[{hr.horizon}d] Sharpe > 0.8"] = m.get("sharpe", 0) > 0.8
        gates[f"[{hr.horizon}d] MaxDD < 20%"] = abs(m.get("max_drawdown_pct", 0)) < 20
        gates[f"[{hr.horizon}d] Positive CAGR"] = m.get("cagr_pct", 0) > 0
        gates[f"[{hr.horizon}d] At least 30 trades"] = m.get("total_trades", 0) >= 30
        gates[f"[{hr.horizon}d] Win rate > 40%"] = m.get("win_rate_pct", 0) > 40
    return gates


def run_backtest_suite(config: Optional[BacktestConfig] = None) -> list[HorizonResult]:
    if config is None:
        config = BacktestConfig()

    symbols = resolve_universe(config.universe)
    print(f"\nLoading data for {len(symbols)} stocks ({config.universe})...")
    data = fetch_nifty_50_data(years=config.years)
    data = {s: data[s] for s in data if s in symbols}
    print(f"Loaded {len(data)} stocks.")

    results = []
    for horizon in config.horizons:
        print(f"\nProcessing horizon {horizon}d...")
        char_data = precompute_all_characteristics(data, window=horizon)
        hr = run_horizon(data, char_data, horizon, config)
        results.append(hr)
        m = hr.metrics
        if m.get("status") not in ("insufficient_data", "no_data"):
            print(f"  CAGR: {m['cagr_pct']:.2f}%  Sharpe: {m['sharpe']:.2f}  "
                  f"MaxDD: {m['max_drawdown_pct']:.2f}%  Trades: {m['total_trades']}")
        else:
            print(f"  {m.get('status', 'error')}")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Comprehensive backtest for Volatility Contrarian")
    parser.add_argument("--universe", default="NIFTY50",
                        help="Universe: 'NIFTY50' or comma-separated symbols like 'RELIANCE.NS,TCS.NS'")
    parser.add_argument("--capital", type=float, default=10_000_000,
                        help="Starting capital (default: 10,000,000)")
    parser.add_argument("--horizons", nargs="+", type=int, default=[5, 10, 21],
                        help="Horizons in trading days (default: 5 10 21)")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--years", type=int, default=3, help="Years of data (default: 3)")
    args = parser.parse_args()

    config = BacktestConfig(
        capital=args.capital,
        universe=args.universe,
        horizons=args.horizons,
        start_date=args.start,
        end_date=args.end,
        years=args.years,
    )
    results = run_backtest_suite(config)
    print_report(results, config)
