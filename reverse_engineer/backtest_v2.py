import pandas as pd
import numpy as np
from data import fetch_nifty_50_data
from characteristics import precompute_all_characteristics


CAPITAL = 10_000_000
SLIPPAGE = 0.001
BROKERAGE = 0.0005
MAX_POSITIONS = 10
MIN_POSITIONS = 3
HARD_STOP = -0.08
PROFIT_TARGET_1 = 0.12
PROFIT_TARGET_2 = 0.18
TRAIL_ACTIVATE = 0.10
TRAIL_DISTANCE = 0.12


def run_backtest(horizon=40, years=3):
    print(f"Loading {years} years of NIFTY 50 data...")
    data = fetch_nifty_50_data(years=years)
    print(f"Pre-computing characteristics (window={horizon})...")
    char_data = precompute_all_characteristics(data, window=horizon)
    print("Done.")

    all_dates = sorted(set(
        d for s in char_data for d in char_data[s].index
    ))
    dates = [d for d in all_dates if d >= pd.Timestamp.now() - pd.Timedelta(days=365*years)]
    print(f"Trading days: {len(dates)}")

    portfolio = {
        "cash": CAPITAL,
        "positions": {},
        "equity_curve": [],
        "trades": [],
    }

    for i, current_date in enumerate(dates):
        if i % 30 == 0 and i > 0:
            print(f"  Progress: {i}/{len(dates)} ({100*i//len(dates)}%)")

        today_close = {}
        for s in data:
            if current_date in data[s].index:
                today_close[s] = data[s].loc[current_date, "close"]

        exited = []
        for symbol, pos in list(portfolio["positions"].items()):
            if current_date not in data[symbol].index:
                exited.append(symbol)
                continue
            price = data[symbol].loc[current_date, "close"]
            days_held = (current_date - pos["entry_date"]).days
            ret = price / pos["entry_price"] - 1
            high_since = max(pos.get("high_since_entry", pos["entry_price"]), price)

            close_signal = False
            exit_reason = None

            if ret <= HARD_STOP:
                close_signal, exit_reason = True, "hard_stop"
            elif days_held >= horizon:
                close_signal, exit_reason = True, "time_stop"

            if not close_signal and ret >= TRAIL_ACTIVATE:
                if price <= high_since * (1 - TRAIL_DISTANCE):
                    close_signal, exit_reason = True, "trailing_stop"

            if not close_signal:
                if ret >= PROFIT_TARGET_2 and pos.get("first_target_hit", False):
                    close_signal, exit_reason = True, "profit_target_2"
                elif ret >= PROFIT_TARGET_1:
                    pos["first_target_hit"] = True
                    exit_reason = "profit_target_1_half"
                    exit_price = price * (1 - SLIPPAGE - BROKERAGE)
                    half = pos["shares"] // 2
                    portfolio["cash"] += half * exit_price
                    pos["shares"] -= half

            if close_signal:
                exit_price = price * (1 - SLIPPAGE - BROKERAGE)
                proceeds = pos["shares"] * exit_price
                portfolio["cash"] += proceeds
                pnl = (exit_price / pos["entry_price"] - 1) * 100
                portfolio["trades"].append({
                    "symbol": symbol, "entry_date": pos["entry_date"],
                    "exit_date": current_date, "entry_price": pos["entry_price"],
                    "exit_price": exit_price, "pnl_pct": pnl,
                    "exit_reason": exit_reason, "days_held": days_held,
                })
                exited.append(symbol)

        for s in exited:
            del portfolio["positions"][s]

        if current_date.weekday() == 4:
            max_new = MAX_POSITIONS - len(portfolio["positions"])
            if max_new > 0:
                universe_atr = np.median([
                    char_data[s].loc[current_date, "avg_true_range_pct"]
                    for s in char_data if current_date in char_data[s].index
                ]) if any(current_date in char_data[s].index for s in char_data) else 0
                universe_vol = np.median([
                    char_data[s].loc[current_date, "volatility"]
                    for s in char_data if current_date in char_data[s].index
                ]) if any(current_date in char_data[s].index for s in char_data) else 0
                if pd.isna(universe_atr):
                    universe_atr, universe_vol = 0, 0

                signals = []
                for symbol in char_data:
                    if symbol in portfolio["positions"]:
                        continue
                    if symbol not in data or current_date not in data[symbol].index:
                        continue
                    if current_date not in char_data[symbol].index:
                        continue
                    c = char_data[symbol].loc[current_date]
                    close = data[symbol].loc[current_date, "close"]
                    hv = data[symbol]["high"].rolling(horizon, min_periods=5).max()
                    pvh = close / hv.loc[current_date] if current_date in hv.index else 1
                    dd = c.get("max_drawdown", 0)
                    atr = c.get("avg_true_range_pct", 0)
                    vol = c.get("volatility", 0)
                    gap = c.get("gap_frequency", 0)
                    pvl = c.get("price_vs_low", 1)
                    vma = c.get("volume_vs_ma10", 0)
                    drawdown_ok = not pd.isna(dd) and dd <= -0.08
                    atr_ok = not pd.isna(atr) and atr > universe_atr
                    vol_ok = not pd.isna(vol) and vol > universe_vol
                    gap_ok = not pd.isna(gap) and gap > 0.05
                    price_ok = not pd.isna(pvl) and pvl < 1.05
                    vol_ok_2 = not pd.isna(vma) and vma > 1.0
                    inval_ok = not pd.isna(pvh) and pvh < 0.98
                    if drawdown_ok and atr_ok and vol_ok and gap_ok and price_ok and vol_ok_2 and inval_ok:
                        signals.append(symbol)

                new = [s for s in signals if s not in portfolio["positions"]][:max_new]
                if new:
                    cap_per = portfolio["cash"] / (len(portfolio["positions"]) + len(new) + MIN_POSITIONS)
                    for symbol in new:
                        price = data[symbol].loc[current_date, "close"]
                        ep = price * (1 + SLIPPAGE + BROKERAGE)
                        shares = int(cap_per / ep)
                        if shares > 0 and portfolio["cash"] >= shares * ep:
                            portfolio["cash"] -= shares * ep
                            portfolio["positions"][symbol] = {
                                "entry_price": ep, "entry_date": current_date,
                                "shares": shares, "high_since_entry": ep,
                                "first_target_hit": False,
                            }

        for symbol, pos in portfolio["positions"].items():
            if current_date in data[symbol].index:
                pos["high_since_entry"] = max(pos["high_since_entry"], data[symbol].loc[current_date, "close"])

        pv = sum(
            data[s].loc[current_date, "close"] * pos["shares"]
            for s, pos in portfolio["positions"].items()
            if current_date in data[s].index
        )
        portfolio["equity_curve"].append({
            "date": current_date, "equity": portfolio["cash"] + pv,
            "cash": portfolio["cash"], "positions_value": pv,
            "num_positions": len(portfolio["positions"]),
        })

    return portfolio


def report(pf):
    eq = pd.DataFrame(pf["equity_curve"]).set_index("date")
    eq["returns"] = eq["equity"].pct_change()
    trades = pd.DataFrame(pf["trades"])
    tr = eq["equity"].iloc[-1] / eq["equity"].iloc[0] - 1
    days = (eq.index[-1] - eq.index[0]).days
    cagr = (1 + tr) ** (365 / max(days, 1)) - 1
    vol = eq["returns"].std() * np.sqrt(252)
    rf = 0.065
    sharpe = (eq["returns"].mean() * 252 - rf) / vol if vol > 0 else 0
    cummax = eq["equity"].cummax()
    dd = (eq["equity"] - cummax) / cummax
    mdd = dd.min()
    downside = eq["returns"][eq["returns"] < 0].std() * np.sqrt(252)
    sortino = (eq["returns"].mean() * 252 - rf) / downside if downside > 0 and (eq["returns"] < 0).sum() > 1 else 0
    print(f"\n{'='*70}")
    print(f"BACKTEST RESULTS (Horizon: {days//len(eq)} days avg)")
    print(f"{'='*70}")
    print(f"  Total Return            {tr*100:.2f}%")
    print(f"  CAGR                    {cagr*100:.2f}%")
    print(f"  Volatility              {vol*100:.2f}%")
    print(f"  Sharpe Ratio            {sharpe:.2f}")
    print(f"  Sortino Ratio           {sortino:.2f}")
    print(f"  Max Drawdown            {mdd*100:.2f}%")
    print(f"  Total Trades            {len(trades)}")
    if not trades.empty:
        print(f"  Win Rate                {trades[trades['pnl_pct']>0].shape[0]/len(trades)*100:.1f}%")
        pf_ratio = trades[trades['pnl_pct']>0]['pnl_pct'].sum() / abs(trades[trades['pnl_pct']<0]['pnl_pct'].sum())
        print(f"  Profit Factor           {pf_ratio:.2f}")
        print(f"  Avg Trade PnL           {trades['pnl_pct'].mean():.2f}%")
        print(f"  Avg Days Held           {trades['days_held'].mean():.1f}")
    print(f"\n  Final Equity: INR {eq['equity'].iloc[-1]:,.2f}")
    print(f"  Peak Equity: INR {eq['equity'].max():,.2f}")

    print(f"\n{'='*70}")
    print(f"EXIT REASON BREAKDOWN")
    for reason, g in trades.groupby("exit_reason"):
        print(f"  {reason:<25} {len(g):4d} trades | Avg PnL: {g['pnl_pct'].mean():+.2f}%")

    print(f"\nYEARLY BREAKDOWN:")
    eq["year"] = eq.index.year
    for year, ye in eq.groupby("year"):
        yr = (ye["equity"].iloc[-1] / ye["equity"].iloc[0] - 1) * 100
        md = (ye["equity"].cummax() / ye["equity"] - 1).max() * 100
        yt = trades[trades["exit_date"].dt.year == year] if not trades.empty else pd.DataFrame()
        s = yr_ret_wins = ""
        if len(yt) > 0:
            s = f", Trades={len(yt)}, Win={yt[yt['pnl_pct']>0].shape[0]/len(yt)*100:.0f}%"
        print(f"  {year}: Return={yr:+.2f}%, MaxDD={md:.2f}%{s}")

    print(f"\n{'='*70}")
    print(f"ACCEPTANCE GATES")
    def fmt_val(v):
        if isinstance(v, float):
            return f"{v:.2f}"
        return str(v)

    passes = []
    for name, val, gate in [
        ("Sharpe Ratio > 0.8", sharpe, 0.8),
        ("Max Drawdown < 20%", abs(mdd), 20),
        ("Positive Total Return", tr, 0),
        ("At least 30 trades", len(trades), 30),
    ]:
        if isinstance(gate, float) and abs(gate) < 5:
            p = val > gate
        elif isinstance(gate, (int, float)):
            p = val >= gate
        else:
            p = True
        passes.append(p)
        print(f"  {name:<30} {fmt_val(val):<15} {'✅' if p else '❌'}")
    overall = all(passes)
    print(f"\n  OVERALL: {'✅ PASSED' if overall else '❌ REJECTED'}")
    print(f"{'='*70}\n")
    return overall


if __name__ == "__main__":
    for h in [20, 5, 40]:
        print(f"\n{'#'*70}")
        print(f"# HORIZON: {h} TRADING DAYS")
        print(f"{'#'*70}")
        pf = run_backtest(horizon=h)
        report(pf)
