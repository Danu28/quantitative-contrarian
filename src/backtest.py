from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.db import DB_PATH, load_data, load_universe
from src.features import precompute_all_characteristics

CAPITAL = 10_000_000
SLIPPAGE = 0.001
BROKERAGE = 0.0005
MAX_POSITIONS = 10
HARD_STOP = -0.08
PROFIT_TARGET_1 = 0.12
PROFIT_TARGET_2 = 0.18
TRAIL_ACTIVATE = 0.10
TRAIL_DISTANCE = 0.12
TIME_STOP_DAYS = 20
MAX_DAILY_LOSS = 0.02
MAX_DRAWDOWN_DISABLE = 0.15
REGIME_NORMAL = 1.0
REGIME_REDUCED = 0.5

ENTRY_DRAWDOWN = -0.08
ENTRY_VOLUME_RATIO = 1.0
ENTRY_PRICE_VS_LOW = 1.05
ENTRY_PRICE_VS_HIGH_MAX = 0.98
HORIZON = 20


def equal_weight_conviction(signals: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return signals
    features = ["max_drawdown", "avg_true_range_pct", "volatility", "price_vs_low", "volume_vs_ma10"]
    weights = []
    for f in features:
        col = signals[f].copy()
        if f == "max_drawdown":
            col = col.abs()
        elif f == "price_vs_low":
            col = (1.05 - col).clip(lower=0)
        rank = col.rank(pct=True)
        weights.append(rank)
    signals["conviction"] = sum(weights) / len(weights)
    return signals


def generate_signals(
    data: dict[str, pd.DataFrame],
    char_data: dict[str, pd.DataFrame],
    date: pd.Timestamp,
) -> pd.DataFrame:
    universe_atr = np.median([
        char_data[s].loc[date, "avg_true_range_pct"]
        for s in char_data if date in char_data[s].index
    ])
    universe_vol = np.median([
        char_data[s].loc[date, "volatility"]
        for s in char_data if date in char_data[s].index
    ])
    if pd.isna(universe_atr):
        return pd.DataFrame()

    signals = []
    for symbol in char_data:
        if symbol not in data or date not in data[symbol].index:
            continue
        if date not in char_data[symbol].index:
            continue
        df = data[symbol]
        c = char_data[symbol].loc[date]
        close = df.loc[date, "close"]
        hv = df["high"].rolling(HORIZON, min_periods=5).max()
        pvh = close / hv.loc[date] if date in hv.index else 1

        dd = c.get("max_drawdown", 0)
        atr = c.get("avg_true_range_pct", 0)
        vol = c.get("volatility", 0)
        pvl = c.get("price_vs_low", 1)
        vma = c.get("volume_vs_ma10", 0)

        ok = True
        ok &= not pd.isna(dd) and dd <= ENTRY_DRAWDOWN
        ok &= not pd.isna(pvl) and pvl < ENTRY_PRICE_VS_LOW
        ok &= not pd.isna(vma) and vma > ENTRY_VOLUME_RATIO
        ok &= not pd.isna(pvh) and pvh < ENTRY_PRICE_VS_HIGH_MAX
        ok &= not pd.isna(atr) and atr > universe_atr
        ok &= not pd.isna(vol) and vol > universe_vol

        if ok:
            signals.append({
                "symbol": symbol,
                "close": close,
                "max_drawdown": dd,
                "avg_true_range_pct": atr,
                "volatility": vol,
                "price_vs_low": pvl,
                "volume_vs_ma10": vma,
                "price_vs_high": pvh,
            })

    result = pd.DataFrame(signals)
    if not result.empty:
        result = equal_weight_conviction(result)
        result = result.sort_values("conviction", ascending=False).reset_index(drop=True)
        result["rank"] = range(1, len(result) + 1)
    return result


class Portfolio:
    def __init__(self, capital: float = CAPITAL):
        self.cash = capital
        self.positions: dict[str, dict] = {}
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self.starting_capital = capital
        self.peak_equity = capital
        self.daily_loss_today = 0
        self.disabled = False

    def total_equity(self, current_prices: dict[str, float] | None = None) -> float:
        pv = 0
        if current_prices:
            for s, pos in self.positions.items():
                price = current_prices.get(s)
                if price is not None:
                    pv += price * pos["shares"]
        return self.cash + pv

    def entry_cost(self, price: float, shares: int) -> float:
        return shares * price * (1 + SLIPPAGE + BROKERAGE)

    def exit_value(self, price: float, shares: int) -> float:
        return shares * price * (1 - SLIPPAGE - BROKERAGE)

    def update_high_since_entry(self, symbol: str, price: float):
        if symbol in self.positions:
            pos = self.positions[symbol]
            pos["high_since_entry"] = max(pos.get("high_since_entry", pos["entry_price"]), price)

    def evaluate_exits(self, symbol: str, price: float, current_date: pd.Timestamp) -> tuple[bool, str | None, bool]:
        pos = self.positions.get(symbol)
        if pos is None:
            return False, None, False
        days_held = (current_date - pos["entry_date"]).days
        ret = price / pos["entry_price"] - 1
        high_since = pos.get("high_since_entry", pos["entry_price"])

        if ret <= HARD_STOP:
            return True, "hard_stop", False
        if days_held >= TIME_STOP_DAYS:
            return True, "time_stop", False
        if ret >= TRAIL_ACTIVATE and price <= high_since * (1 - TRAIL_DISTANCE):
            return True, "trailing_stop", False
        if pos.get("first_target_hit", False) and ret >= PROFIT_TARGET_2:
            return True, "profit_target_2", False
        if not pos.get("first_target_hit", False) and ret >= PROFIT_TARGET_1:
            return True, "profit_target_1_half", True
        return False, None, False

    def exit_position(self, symbol: str, price: float, current_date: pd.Timestamp, exit_reason: str):
        pos = self.positions.pop(symbol, None)
        if pos is None:
            return
        exit_price = price * (1 - SLIPPAGE - BROKERAGE)
        proceeds = pos["shares"] * exit_price
        self.cash += proceeds
        days_held = (current_date - pos["entry_date"]).days
        pnl_pct = (exit_price / pos["entry_price"] - 1) * 100
        self.trades.append({
            "symbol": symbol,
            "entry_date": pos["entry_date"],
            "exit_date": current_date,
            "entry_price": pos["entry_price"],
            "exit_price": exit_price,
            "pnl_pct": pnl_pct,
            "exit_reason": exit_reason,
            "days_held": days_held,
        })
        if pnl_pct < 0:
            self.daily_loss_today += abs(pnl_pct) * pos["shares"] * pos["entry_price"] / 100

    def exit_half_position(self, symbol: str, price: float, current_date: pd.Timestamp):
        pos = self.positions.get(symbol)
        if pos is None or pos["first_target_hit"]:
            return
        exit_price = price * (1 - SLIPPAGE - BROKERAGE)
        half_shares = pos["shares"] // 2
        proceeds = half_shares * exit_price
        self.cash += proceeds
        pos["shares"] -= half_shares
        pos["first_target_hit"] = True

    def process_day(self, signals: pd.DataFrame, prices: dict[str, float], current_date: pd.Timestamp, regime_multiplier: float = REGIME_NORMAL):
        self.daily_loss_today = 0

        for s in list(self.positions.keys()):
            price = prices.get(s)
            if price is None:
                continue
            self.update_high_since_entry(s, price)
            should_exit, reason, is_half = self.evaluate_exits(s, price, current_date)
            if should_exit and reason:
                if is_half:
                    self.exit_half_position(s, price, current_date)
                else:
                    self.exit_position(s, price, current_date, reason)

        if current_date.weekday() == 4 and not self.disabled:
            self._rebalance(signals, prices, current_date, regime_multiplier)

        for s in list(self.positions.keys()):
            price = prices.get(s)
            if price is not None:
                self.update_high_since_entry(s, price)

        pv = sum(prices.get(s, 0) * pos["shares"] for s, pos in self.positions.items())
        total = self.cash + pv
        self.peak_equity = max(self.peak_equity, total)
        drawdown = (self.peak_equity - total) / self.peak_equity

        if drawdown >= MAX_DRAWDOWN_DISABLE:
            self.disabled = True
            for s in list(self.positions.keys()):
                price = prices.get(s)
                if price is not None:
                    self.exit_position(s, price, current_date, "emergency_drawdown")

        self.equity_curve.append({
            "date": current_date, "equity": total, "cash": self.cash,
            "positions_value": pv, "num_positions": len(self.positions), "daily_pnl_pct": None,
        })

        if len(self.equity_curve) >= 2:
            prev_eq = self.equity_curve[-2]["equity"]
            self.equity_curve[-1]["daily_pnl_pct"] = (total / prev_eq - 1) * 100

    MIN_POSITIONS = 3

    def _rebalance(self, signals: pd.DataFrame, prices: dict[str, float], current_date: pd.Timestamp, regime_multiplier: float):
        max_new = int(MAX_POSITIONS * regime_multiplier)
        max_new = max(max_new, 0)
        signal_symbols = set(signals["symbol"].values) if not signals.empty else set()

        for s in list(self.positions.keys()):
            if s not in signal_symbols:
                price = prices.get(s)
                if price is not None:
                    self.exit_position(s, price, current_date, "not_in_universe")

        remaining = max_new - len(self.positions)
        if remaining <= 0:
            return
        candidates = [s for s in signal_symbols if s not in self.positions][:remaining]
        if not candidates:
            return

        cap_per = self.cash / (len(self.positions) + len(candidates) + self.MIN_POSITIONS)
        for symbol in candidates:
            price = prices.get(symbol)
            if price is None:
                continue
            ep = price * (1 + SLIPPAGE + BROKERAGE)
            shares = int(cap_per / ep)
            if shares > 0 and self.cash >= shares * ep:
                self.cash -= shares * ep
                self.positions[symbol] = {
                    "entry_price": ep, "entry_date": current_date, "shares": shares,
                    "high_since_entry": ep, "first_target_hit": False,
                }

    def get_positions_summary(self) -> pd.DataFrame:
        rows = []
        for symbol, pos in self.positions.items():
            rows.append({
                "symbol": symbol, "entry_date": pos["entry_date"],
                "entry_price": pos["entry_price"], "shares": pos["shares"],
                "high_since_entry": pos.get("high_since_entry", pos["entry_price"]),
                "first_target_hit": pos.get("first_target_hit", False),
            })
        return pd.DataFrame(rows)

    def get_trades_summary(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame(self.trades)

    def get_performance(self) -> dict:
        eq = pd.DataFrame(self.equity_curve).set_index("date")
        if len(eq) < 2:
            return {"status": "insufficient_data"}
        total_ret = eq["equity"].iloc[-1] / eq["equity"].iloc[0] - 1
        days = (eq.index[-1] - eq.index[0]).days
        cagr = (1 + total_ret) ** (365 / max(days, 1)) - 1
        returns = eq["equity"].pct_change().dropna()
        vol = returns.std() * np.sqrt(252)
        rf = 0.065
        sharpe = (returns.mean() * 252 - rf) / vol if vol > 0 else 0
        cummax = eq["equity"].cummax()
        dd = (eq["equity"] - cummax) / cummax
        mdd = dd.min()
        downside = returns[returns < 0].std() * np.sqrt(252)
        sortino = (returns.mean() * 252 - rf) / downside if downside > 0 and (returns < 0).sum() > 1 else 0
        trades_df = self.get_trades_summary()
        win_rate = 0
        profit_factor = 0
        if not trades_df.empty:
            win_rate = (trades_df["pnl_pct"] > 0).sum() / len(trades_df) * 100
            pos_sum = trades_df[trades_df["pnl_pct"] > 0]["pnl_pct"].sum()
            neg_sum = abs(trades_df[trades_df["pnl_pct"] < 0]["pnl_pct"].sum())
            profit_factor = pos_sum / neg_sum if neg_sum > 0 else float("inf")
        return {
            "total_return_pct": total_ret * 100, "cagr_pct": cagr * 100,
            "volatility_pct": vol * 100, "sharpe": sharpe, "sortino": sortino,
            "max_drawdown_pct": mdd * 100, "total_trades": len(trades_df),
            "win_rate_pct": win_rate, "profit_factor": profit_factor,
            "final_equity": eq["equity"].iloc[-1], "peak_equity": self.peak_equity,
            "num_positions": len(self.positions), "disabled": self.disabled,
        }


@dataclass
class BacktestConfig:
    capital: float = CAPITAL
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
        "total_return_pct": total_ret * 100, "cagr_pct": cagr * 100,
        "volatility_pct": vol * 100, "downside_dev_pct": downside * 100,
        "sharpe": sharpe, "sortino": sortino, "calmar": calmar,
        "recovery_factor": recovery, "max_drawdown_pct": mdd * 100,
        "avg_drawdown_pct": avg_dd * 100, "total_trades": len(trades),
        "win_rate_pct": win_rate, "loss_rate_pct": 100 - win_rate,
        "profit_factor": profit_factor, "expectancy_pct": expectancy,
        "avg_gain_pct": avg_gain, "avg_loss_pct": avg_loss,
        "largest_win_pct": largest_win, "largest_loss_pct": largest_loss,
        "avg_hold_days": avg_hold, "avg_exposure_pct": exposure,
        "turnover_per_year": turnover, "final_equity": eq["equity"].iloc[-1],
        "peak_equity": eq["equity"].max(),
    }


def run_horizon(data: dict, char_data: dict, horizon: int, config: BacktestConfig) -> HorizonResult:
    all_dates = sorted(set(d for s in char_data for d in char_data[s].index))
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
    return HorizonResult(horizon=horizon, trades=trades, equity=eq, metrics=metrics, exposure=exposure, monthly_returns=monthly)


def print_report(results: list[HorizonResult], config: BacktestConfig):
    sep = "=" * 78
    print(f"\n{sep}")
    print("  VOLATILITY CONTRARIAN - COMPREHENSIVE BACKTEST REPORT")
    print(f"  Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Capital: INR {config.capital:,.0f}")
    print(f"  Slippage: {config.slippage:.1%} | Brokerage: {config.brokerage:.1%}")
    print(f"{sep}")

    print(f"\n{'-' * 78}")
    print("  1. EXECUTIVE SUMMARY")
    print(f"{'-' * 78}")
    best = max(results, key=lambda r: r.metrics.get("cagr_pct", -999))
    worst = min(results, key=lambda r: r.metrics.get("cagr_pct", -999))
    print(f"  Best horizon:     {best.horizon}d (CAGR {best.metrics.get('cagr_pct', 0):.2f}%)")
    print(f"  Worst horizon:    {worst.horizon}d (CAGR {worst.metrics.get('cagr_pct', 0):.2f}%)")

    for hr in results:
        h = hr.horizon
        m = hr.metrics
        eq = hr.equity
        trades = hr.trades
        print(f"\n{'-' * 78}")
        print(f"  2. HORIZON {h} TRADING DAYS - RESULTS")
        print(f"{'-' * 78}")
        if m.get("status") in ("insufficient_data", "no_data"):
            print(f"  Insufficient data for horizon {h}")
            continue
        first_date = eq.index[0].date() if not eq.empty else "N/A"
        last_date = eq.index[-1].date() if not eq.empty else "N/A"
        print(f"  Period: {first_date} -> {last_date} ({len(eq)} trading days)")
        print(f"\n  Return Metrics:")
        print(f"    Total Return: {m['total_return_pct']:>9.2f}%")
        print(f"    CAGR:         {m['cagr_pct']:>9.2f}%")
        print(f"  Risk Metrics:")
        print(f"    Volatility:   {m['volatility_pct']:>9.2f}%")
        print(f"    Max Drawdown: {m['max_drawdown_pct']:>9.2f}%")
        print(f"  Risk-Adjusted:")
        print(f"    Sharpe:       {m['sharpe']:>9.2f}")
        print(f"    Sortino:      {m['sortino']:>9.2f}")
        print(f"  Trade Metrics:")
        print(f"    Total Trades: {m['total_trades']:>9}")
        print(f"    Win Rate:     {m['win_rate_pct']:>8.1f}%")
        print(f"    Profit Fact:  {m['profit_factor']:>9.2f}")
        print(f"    Avg Hold:     {m['avg_hold_days']:>8.1f} days")
        if not trades.empty:
            print(f"\n  Exit Reason Breakdown:")
            for reason, g in trades.groupby("exit_reason"):
                avg = g["pnl_pct"].mean()
                wins = (g["pnl_pct"] > 0).sum()
                print(f"    {reason:<20}  {len(g):4d} trades  Avg: {avg:+.2f}%  Win: {wins}/{len(g)}")

    print(f"\n{'-' * 78}")
    print("  3. CROSS-HORIZON COMPARISON")
    print(f"{'-' * 78}")
    print(f"  {'Horizon':<10} {'CAGR':>8} {'MaxDD':>8} {'Sharpe':>8} {'WinRate':>8} {'Trades':>8}")
    for hr in sorted(results, key=lambda r: r.horizon):
        m = hr.metrics
        print(f"  {hr.horizon:>4}d      {m.get('cagr_pct', 0):>7.2f}% {m.get('max_drawdown_pct', 0):>7.2f}% {m.get('sharpe', 0):>7.2f} {m.get('win_rate_pct', 0):>6.1f}% {m.get('total_trades', 0):>7}")

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


def run_backtest(
    universe_slug_or_path: str,
    years: int = 3,
    capital: float = CAPITAL,
    horizons: list[int] | None = None,
    db_path: str | Path = DB_PATH,
) -> list[HorizonResult]:
    if horizons is None:
        horizons = [5, 10, 21]
    config = BacktestConfig(capital=capital, horizons=horizons, years=years)

    config_data = load_universe(universe_slug_or_path)
    symbols = config_data["symbols"]
    print(f"Loading data for {len(symbols)} stocks...")
    df_all = load_data(universe_slug_or_path, db_path=db_path)
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=365 * years)
    df_all = df_all[df_all["date"] >= cutoff]
    data: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        sub = df_all[df_all["symbol"] == sym].copy()
        if sub.empty:
            continue
        sub = sub.set_index("date")
        sub.index = pd.DatetimeIndex(sub.index)
        data[sym] = sub
    print(f"Loaded {len(data)} stocks.")

    results = []
    for horizon in horizons:
        print(f"\nProcessing horizon {horizon}d...")
        char_data = precompute_all_characteristics(data, window=horizon)
        hr = run_horizon(data, char_data, horizon, config)
        results.append(hr)
        m = hr.metrics
        if m.get("status") not in ("insufficient_data", "no_data"):
            print(f"  CAGR: {m['cagr_pct']:.2f}%  Sharpe: {m['sharpe']:.2f}  MaxDD: {m['max_drawdown_pct']:.2f}%  Trades: {m['total_trades']}")
        else:
            print(f"  {m.get('status', 'error')}")

    return results
