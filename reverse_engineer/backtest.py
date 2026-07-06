import pandas as pd
import numpy as np
from data import fetch_nifty_50_data, fetch_index_data
from characteristics import precompute_all_characteristics, get_characteristic_names


CAPITAL = 10_000_000
SLIPPAGE = 0.001
BROKERAGE = 0.0005
MAX_POSITIONS = 10
MIN_POSITIONS = 3
HARD_STOP = -0.08
PROFIT_TARGET_1 = 0.10
PROFIT_TARGET_2 = 0.15
TIME_STOP = 20
TRAIL_ACTIVATE = 0.08
TRAIL_DISTANCE = 0.10


def compute_signal(data, char_data, date):
    signals = []
    universe_median_atr = np.median([
        char_data[s].loc[date, "avg_true_range_pct"]
        for s in char_data if date in char_data[s].index
    ])
    universe_median_vol = np.median([
        char_data[s].loc[date, "volatility"]
        for s in char_data if date in char_data[s].index
    ])
    if pd.isna(universe_median_atr) or pd.isna(universe_median_vol):
        return signals
    for symbol in char_data:
        if symbol not in data:
            continue
        df = data[symbol]
        if date not in df.index or date not in char_data[symbol].index:
            continue

        c = char_data[symbol].loc[date]
        close = df.loc[date, "close"]
        price_vs_high = close / df["high"].rolling(20, min_periods=5).max().loc[date] if date in df.index else 1

        drawdown = c.get("max_drawdown", 0)
        atr = c.get("avg_true_range_pct", 0)
        vol = c.get("volatility", 0)
        volume = c.get("avg_volume", 0)
        vol_ma = c.get("volume_vs_ma10", 0)
        price_vs_low = c.get("price_vs_low", 1)
        gap_freq = c.get("gap_frequency", 0)

        meets = True
        meets &= not pd.isna(drawdown) and drawdown <= -0.08
        meets &= not pd.isna(atr) and atr > universe_median_atr
        meets &= not pd.isna(vol) and vol > universe_median_vol
        meets &= not pd.isna(volume) and volume > 0
        meets &= not pd.isna(vol_ma) and vol_ma > 1.0
        meets &= not pd.isna(price_vs_low) and price_vs_low < 1.05
        meets &= not pd.isna(gap_freq) and gap_freq > 0.05
        meets &= not pd.isna(price_vs_high) and price_vs_high < 0.98

        if meets:
            signals.append(symbol)
    return signals


def backtest(start_date, end_date, initial_capital=CAPITAL, walk_forward_months=6):
    print(f"Loading data: {start_date.date()} to {end_date.date()}")
    data = fetch_nifty_50_data(years=5)
    print(f"Pre-computing characteristics...")
    char_data = precompute_all_characteristics(data, window=20)
    print("Done.")

    dates = sorted(set(
        d for s in char_data for d in char_data[s].index
        if start_date <= d <= end_date
    ))
    print(f"Trading days: {len(dates)}")

    portfolio = {
        "cash": initial_capital,
        "positions": {},
        "equity_curve": [],
        "trades": [],
    }

    train_end = dates[0]
    for i, current_date in enumerate(dates):
        if i % 20 == 0 and i > 0:
            print(f"  Progress: {i}/{len(dates)} ({100*i//len(dates)}%)")

        today_close = {}
        for s in data:
            if current_date in data[s].index:
                today_close[s] = data[s].loc[current_date, "close"]

        exited = []
        for symbol, pos in portfolio["positions"].items():
            if current_date not in data[symbol].index:
                exited.append(symbol)
                continue
            price = data[symbol].loc[current_date, "close"]
            days_held = (current_date - pos["entry_date"]).days
            ret = price / pos["entry_price"] - 1
            high_since_entry = pos.get("high_since_entry", pos["entry_price"])

            close_signal = False
            exit_reason = None

            if ret <= HARD_STOP:
                close_signal = True
                exit_reason = "hard_stop"
            elif days_held >= TIME_STOP:
                close_signal = True
                exit_reason = "time_stop"

            if not close_signal and ret >= TRAIL_ACTIVATE:
                trail_stop = high_since_entry * (1 - TRAIL_DISTANCE)
                if price <= trail_stop:
                    close_signal = True
                    exit_reason = "trailing_stop"

            if not close_signal:
                if ret >= PROFIT_TARGET_2 and pos.get("first_target_hit", False):
                    close_signal = True
                    exit_reason = "profit_target_2"
                elif ret >= PROFIT_TARGET_1:
                    pos["first_target_hit"] = True
                    exit_reason = "profit_target_1_half"
                    exit_price = price * (1 - SLIPPAGE - BROKERAGE)
                    half_shares = pos["shares"] // 2
                    proceeds = half_shares * exit_price
                    portfolio["cash"] += proceeds
                    pos["shares"] -= half_shares
                    pos["entry_price"] = pos["entry_price"]

            if close_signal:
                exit_price = price * (1 - SLIPPAGE - BROKERAGE)
                proceeds = pos["shares"] * exit_price
                portfolio["cash"] += proceeds
                pnl = (exit_price / pos["entry_price"] - 1) * 100
                portfolio["trades"].append({
                    "symbol": symbol,
                    "entry_date": pos["entry_date"],
                    "exit_date": current_date,
                    "entry_price": pos["entry_price"],
                    "exit_price": exit_price,
                    "shares": pos["shares"],
                    "pnl_pct": pnl,
                    "exit_reason": exit_reason,
                    "days_held": days_held,
                })
                exited.append(symbol)

        for s in exited:
            del portfolio["positions"][s]

        if current_date.weekday() == 4:
            max_new = MAX_POSITIONS - len(portfolio["positions"])
            if max_new > 0:
                signals = compute_signal(data, char_data, current_date)
                new_signals = [s for s in signals if s not in portfolio["positions"]][:max_new]
                if new_signals:
                    capital_per = portfolio["cash"] / (len(portfolio["positions"]) + len(new_signals) + MIN_POSITIONS)
                    for symbol in new_signals:
                        price = data[symbol].loc[current_date, "close"]
                        entry_price = price * (1 + SLIPPAGE + BROKERAGE)
                        shares = int(capital_per / entry_price)
                        if shares > 0 and portfolio["cash"] >= shares * entry_price:
                            portfolio["cash"] -= shares * entry_price
                            portfolio["positions"][symbol] = {
                                "entry_price": entry_price,
                                "entry_date": current_date,
                                "shares": shares,
                                "high_since_entry": entry_price,
                                "first_target_hit": False,
                            }

        for symbol, pos in portfolio["positions"].items():
            if current_date in data[symbol].index:
                price = data[symbol].loc[current_date, "close"]
                pos["high_since_entry"] = max(pos["high_since_entry"], price)

        position_value = sum(
            data[s].loc[current_date, "close"] * pos["shares"]
            for s, pos in portfolio["positions"].items()
            if current_date in data[s].index
        )
        total_equity = portfolio["cash"] + position_value
        portfolio["equity_curve"].append({
            "date": current_date,
            "equity": total_equity,
            "cash": portfolio["cash"],
            "positions_value": position_value,
            "num_positions": len(portfolio["positions"]),
        })

    return portfolio


def compute_metrics(portfolio):
    eq = pd.DataFrame(portfolio["equity_curve"]).set_index("date")
    eq["returns"] = eq["equity"].pct_change()
    trades = pd.DataFrame(portfolio["trades"])
    total_return = (eq["equity"].iloc[-1] / eq["equity"].iloc[0] - 1)
    days = (eq.index[-1] - eq.index[0]).days
    cagr = (1 + total_return) ** (365 / max(days, 1)) - 1
    volatility = eq["returns"].std() * np.sqrt(252)
    rf = 0.065
    sharpe = (eq["returns"].mean() * 252 - rf) / volatility if volatility > 0 else 0
    cummax = eq["equity"].cummax()
    drawdown = (eq["equity"] - cummax) / cummax
    max_dd = drawdown.min()
    sortino = (eq["returns"].mean() * 252 - rf) / (eq["returns"][eq["returns"] < 0].std() * np.sqrt(252)) if (eq["returns"] < 0).sum() > 1 else 0
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0

    metrics = {
        "Total Return": f"{total_return*100:.2f}%",
        "CAGR": f"{cagr*100:.2f}%",
        "Volatility": f"{volatility*100:.2f}%",
        "Sharpe Ratio": f"{sharpe:.2f}",
        "Sortino Ratio": f"{sortino:.2f}",
        "Calmar Ratio": f"{calmar:.2f}",
        "Max Drawdown": f"{max_dd*100:.2f}%",
        "Total Trades": len(trades) if not trades.empty else 0,
        "Win Rate": f"{trades[trades['pnl_pct'] > 0].shape[0] / max(len(trades), 1) * 100:.1f}%" if not trades.empty else "N/A",
        "Profit Factor": f"{trades[trades['pnl_pct'] > 0]['pnl_pct'].sum() / abs(trades[trades['pnl_pct'] < 0]['pnl_pct'].sum()):.2f}" if not trades.empty and trades[trades['pnl_pct'] < 0]['pnl_pct'].sum() != 0 else "N/A",
        "Avg Trade PnL": f"{trades['pnl_pct'].mean():.2f}%" if not trades.empty else "N/A",
        "Avg Days Held": f"{trades['days_held'].mean():.1f}" if not trades.empty else "N/A",
    }
    return metrics, drawdown, eq, trades


def print_backtest_report(metrics, drawdown, eq, trades):
    print(f"\n{'='*70}")
    print(f"BACKTEST RESULTS")
    print(f"{'='*70}")
    for k, v in metrics.items():
        print(f"  {k:<25} {v}")
    print(f"\n  Final Equity: ₹{eq['equity'].iloc[-1]:,.2f}")
    print(f"  Peak Equity: ₹{eq['equity'].max():,.2f}")
    print(f"  Worst Drawdown Date: {drawdown.idxmin().date()} ({drawdown.min()*100:.2f}%)")
    print(f"\n{'='*70}")
    print(f"EXIT REASON BREAKDOWN")
    if not trades.empty:
        for reason, group in trades.groupby("exit_reason"):
            print(f"  {reason:<25} {len(group):4d} trades | Avg PnL: {group['pnl_pct'].mean():+.2f}%")
    print(f"{'='*70}")

    print(f"\nYEARLY BREAKDOWN:")
    eq["year"] = eq.index.year
    for year, year_eq in eq.groupby("year"):
        yr_ret = (year_eq["equity"].iloc[-1] / year_eq["equity"].iloc[0] - 1) * 100
        yr_max = (year_eq["equity"].cummax() / year_eq["equity"] - 1).max() * 100
        yr_trades = trades[trades["exit_date"].dt.year == year] if not trades.empty else pd.DataFrame()
        print(f"  {year}: Return={yr_ret:+.2f}%, MaxDD={yr_max:.2f}%, Trades={len(yr_trades)}")


def run_full_validation():
    from datetime import datetime, timedelta
    end = datetime.now()
    start = end - timedelta(days=365 * 3)
    pf = backtest(start.replace(tzinfo=None), end.replace(tzinfo=None))
    metrics, drawdown, eq, trades = compute_metrics(pf)
    print_backtest_report(metrics, drawdown, eq, trades)

    acceptance_gates = {
        "Sharpe Ratio > 0.8": metrics["Sharpe Ratio"],
        "Max Drawdown < 20%": metrics["Max Drawdown"],
        "Positive Total Return": metrics["Total Return"],
        "At least 30 trades": metrics["Total Trades"],
    }
    print(f"\n{'='*70}")
    print(f"ACCEPTANCE GATES")
    print(f"{'='*70}")
    all_pass = True
    for gate, value in acceptance_gates.items():
        actual = float(value.replace("%", "").replace(",", "")) if isinstance(value, str) else float(value) if value else 0
        if "Sharpe" in gate:
            passed = actual > 0.8
        elif "Drawdown" in gate:
            passed = actual < 20
        elif "Return" in gate:
            passed = actual > 0
        elif "trades" in gate:
            passed = actual >= 30
        else:
            passed = True
        status = "✅" if passed else "❌"
        print(f"  {gate:<30} {value:<15} {status}")
        if not passed:
            all_pass = False

    print(f"\n  OVERALL: {'✅ PASSED' if all_pass else '❌ REJECTED — see above gates for details'}")
    print(f"{'='*70}\n")
    return metrics, all_pass


if __name__ == "__main__":
    run_full_validation()
