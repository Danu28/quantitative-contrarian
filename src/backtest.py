from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src.db import DB_PATH, load_data, load_symbol_data, load_universe, get_sector_map
from src.features import precompute_all_characteristics
from src.config import (
    CAPITAL, SLIPPAGE, BROKERAGE, MAX_POSITIONS, MIN_POSITIONS,
    HARD_STOP, PROFIT_TARGET_1, PROFIT_TARGET_2, TRAIL_ACTIVATE,
    TRAIL_DISTANCE, TIME_STOP_DAYS, MAX_DAILY_LOSS, MAX_DRAWDOWN_DISABLE,
    REGIME_NORMAL, ENTRY_DRAWDOWN, ENTRY_VOLUME_RATIO,
    ENTRY_PRICE_VS_LOW, ENTRY_PRICE_VS_HIGH_MAX, HORIZON,
    MAX_SECTOR_POSITIONS,
    MOM_MAX_POSITIONS, MOM_MIN_POSITIONS, MOM_STOP_LOSS,
    MOM_TRAIL_ACTIVATE, MOM_TRAIL_DISTANCE, MOM_MIN_VOLUME,
    MOM_LOOKBACK, MOM_MAX_PRICE, MOM_MIN_PRICE,
    MOM_SECTOR_MAX,
)


def weighted_conviction(signals: pd.DataFrame) -> pd.DataFrame:
    """Research-weighted conviction using features with significant predictive power."""
    if signals.empty:
        return signals
    ranks = []
    for feat in ["gap_frequency", "avg_true_range_pct", "avg_up_day", "volatility"]:
        col = signals[feat].fillna(signals[feat].median())
        ranks.append(col.rank(pct=True))
    for feat in ["price_vs_ma10", "price_vs_high", "ma_slope_5", "ret_3d"]:
        col = signals[feat].fillna(signals[feat].median())
        ranks.append(1 - col.rank(pct=True))
    weights = [0.19, 0.18, 0.17, 0.12, 0.17, 0.16, 0.17, 0.13]
    signals["conviction"] = sum(w * r for w, r in zip(weights, ranks)) / sum(weights)
    return signals


def generate_signals(
    data: dict[str, pd.DataFrame],
    char_data: dict[str, pd.DataFrame],
    date: pd.Timestamp,
    horizon: int = HORIZON,
) -> pd.DataFrame:
    atr_vals = [char_data[s].loc[date, "avg_true_range_pct"]
                for s in char_data if date in char_data[s].index]
    universe_atr = np.median(atr_vals) if atr_vals else np.nan

    vol_vals = [char_data[s].loc[date, "volatility"]
                for s in char_data if date in char_data[s].index]
    universe_vol = np.median(vol_vals) if vol_vals else np.nan
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
        hv = df["high"].rolling(horizon, min_periods=5).max()
        pvh = close / hv.loc[date] if date in hv.index else 1

        dd = c.get("max_drawdown", 0)
        atr = c.get("avg_true_range_pct", 0)
        vol = c.get("volatility", 0)
        pvl = c.get("price_vs_low", 1)
        vma = c.get("volume_vs_ma10", 0)
        gap_freq = c.get("gap_frequency", 0)
        avg_up = c.get("avg_up_day", 0)
        pv_ma10 = c.get("price_vs_ma10", 1)
        ma_s5 = c.get("ma_slope_5", 0)
        ret_3d = c.get("ret_3d", 0)

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
                "gap_frequency": gap_freq,
                "avg_up_day": avg_up,
                "price_vs_ma10": pv_ma10,
                "ma_slope_5": ma_s5,
                "ret_3d": ret_3d,
            })

    result = pd.DataFrame(signals)
    if not result.empty:
        result = weighted_conviction(result)
        result = result.sort_values("conviction", ascending=False).reset_index(drop=True)
        result["rank"] = range(1, len(result) + 1)
    return result


def generate_momentum_signals(
    data: dict[str, pd.DataFrame],
    date: pd.Timestamp,
    avg_vol_series: pd.Series | None = None,
) -> pd.DataFrame:
    """Rank stocks by trailing 12-month momentum, apply filters."""
    lookback_date = date - pd.DateOffset(days=400)
    candidates = []
    for sym in data:
        df = data[sym]
        if date not in df.index:
            continue
        if lookback_date not in df.index and date not in df.index:
            continue
        try:
            past = df.loc[lookback_date:, "close"]
            if len(past) < MOM_LOOKBACK:
                continue
            mom = df.loc[date, "close"] / past.iloc[-MOM_LOOKBACK] - 1
        except (KeyError, IndexError):
            continue

        cp = df.loc[date, "close"]
        if cp < MOM_MIN_PRICE or cp > MOM_MAX_PRICE:
            continue

        vol = df.loc[date, "volume"] if "volume" in df.columns else 0
        if avg_vol_series is not None and sym in avg_vol_series.index:
            if avg_vol_series[sym] < MOM_MIN_VOLUME:
                continue

        candidates.append({
            "symbol": sym,
            "close": cp,
            "momentum_12m": mom,
        })

    if not candidates:
        return pd.DataFrame()

    result = pd.DataFrame(candidates)
    result = result.sort_values("momentum_12m", ascending=False).reset_index(drop=True)
    result["rank"] = range(1, len(result) + 1)
    return result


def compute_momentum_stops(entry_price: float) -> dict:
    return {
        "entry": round(entry_price * (1 + SLIPPAGE + BROKERAGE), 2),
        "hard_stop": round(entry_price * (1 + MOM_STOP_LOSS) * (1 - SLIPPAGE - BROKERAGE), 2),
        "trail_trigger": round(entry_price * (1 + MOM_TRAIL_ACTIVATE), 2),
        "trail_stop": round(entry_price * (1 + MOM_TRAIL_ACTIVATE) * (1 - MOM_TRAIL_DISTANCE) * (1 - SLIPPAGE - BROKERAGE), 2),
    }


class Portfolio:
    def __init__(self, capital: float = CAPITAL, sector_map: dict[str, str] | None = None):
        self.cash = capital
        self.positions: dict[str, dict] = {}
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self.starting_capital = capital
        self.peak_equity = capital
        self.daily_loss_today = 0
        self.disabled = False
        self.sector_map = sector_map or {}

    def sector_count(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for sym in self.positions:
            sector = self.sector_map.get(sym, "Unknown")
            counts[sector] = counts.get(sector, 0) + 1
        return counts

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
        trading_days_held = pos.get("trading_days", 0)
        ret = price / pos["entry_price"] - 1
        high_since = pos.get("high_since_entry", pos["entry_price"])

        if ret <= HARD_STOP:
            return True, "hard_stop", False
        if trading_days_held >= TIME_STOP_DAYS:
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
        trading_days = pos.get("trading_days", 0)
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
            "trading_days": trading_days,
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
            self.positions[s]["trading_days"] = self.positions[s].get("trading_days", 0) + 1
            self.update_high_since_entry(s, price)
            should_exit, reason, is_half = self.evaluate_exits(s, price, current_date)
            if should_exit and reason:
                if is_half:
                    self.exit_half_position(s, price, current_date)
                else:
                    self.exit_position(s, price, current_date, reason)

        if current_date.weekday() == 4 and not self.disabled:
            if self.daily_loss_today <= self.starting_capital * MAX_DAILY_LOSS:
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

    def _rebalance(self, signals: pd.DataFrame, prices: dict[str, float], current_date: pd.Timestamp, regime_multiplier: float):
        max_new = int(MAX_POSITIONS * regime_multiplier)
        max_new = max(max_new, 0)

        remaining = max_new - len(self.positions)
        if remaining <= 0 or signals.empty:
            return
        ranked = signals.sort_values("conviction", ascending=False)
        candidates = [s for s in ranked["symbol"].values if s not in self.positions][:remaining * MAX_SECTOR_POSITIONS]
        if not candidates:
            return

        # Sector concentration: skip candidates in sectors already at limit
        sector_counts = self.sector_count()
        filtered: list[str] = []
        for s in candidates:
            sec = self.sector_map.get(s, "Unknown")
            if sector_counts.get(sec, 0) < MAX_SECTOR_POSITIONS:
                filtered.append(s)
                sector_counts[sec] = sector_counts.get(sec, 0) + 1
            if len(filtered) >= remaining:
                break
        candidates = filtered
        if not candidates:
            return

        cap_per = self.cash / (len(self.positions) + len(candidates) + MIN_POSITIONS)
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
                    "high_since_entry": ep, "first_target_hit": False, "trading_days": 0,
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



def run_horizon(data: dict, char_data: dict, horizon: int, config: BacktestConfig, sector_map: dict[str, str] | None = None) -> HorizonResult:
    all_dates = sorted(set(d for s in char_data for d in char_data[s].index))
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=365 * config.years)
    all_dates = [d for d in all_dates if d >= cutoff]
    if not all_dates:
        return HorizonResult(horizon=horizon, trades=pd.DataFrame(), equity=pd.DataFrame(), metrics={"status": "no_data"}, exposure=pd.Series(), monthly_returns=pd.DataFrame())

    pf = Portfolio(capital=config.capital, sector_map=sector_map)
    for date in all_dates:
        prices = {s: data[s].loc[date, "close"] for s in data if date in data[s].index}
        sig = generate_signals(data, char_data, date, horizon=horizon)
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
    sector_map = get_sector_map(universe_slug_or_path)
    print(f"Loading data for {len(symbols)} stocks...")
    df_all = load_data(universe_slug_or_path, db_path=db_path)
    if years is not None:
        cutoff = pd.Timestamp.now() - pd.DateOffset(days=365 * years)
        df_all = df_all[df_all["date"] >= cutoff]
    data = load_symbol_data(universe_slug_or_path, years=years, db_path=db_path, df_all=df_all)

    # Data quality filter: drop stocks with insufficient history
    # NOTE: This uses current index constituents, not historical ones.
    # True survivorship-bias-free backtesting requires historical constituent lists
    # from the exchange. Using current-only constituents may inflate returns.
    min_date = df_all["date"].min()
    max_date = df_all["date"].max()
    expected_days = (max_date - min_date).days
    before = len(data)
    data = {
        s: df for s, df in data.items()
        if (df.index.max() - df.index.min()).days >= expected_days * 0.9
    }
    dropped = before - len(data)
    if dropped:
        print(f"  Data quality filter: dropped {dropped} stock(s) with insufficient history")

    print(f"Loaded {len(data)} stocks.")

    results = []
    for horizon in horizons:
        print(f"\nProcessing horizon {horizon}d...")
        char_data = precompute_all_characteristics(data, window=horizon)
        hr = run_horizon(data, char_data, horizon, config, sector_map=sector_map)
        results.append(hr)
        m = hr.metrics
        if m.get("status") not in ("insufficient_data", "no_data"):
            print(f"  CAGR: {m['cagr_pct']:.2f}%  Sharpe: {m['sharpe']:.2f}  MaxDD: {m['max_drawdown_pct']:.2f}%  Trades: {m['total_trades']}")
        else:
            print(f"  {m.get('status', 'error')}")

    return results


def find_trading_dates(data: dict[str, pd.DataFrame], date: pd.Timestamp, ahead: int) -> list[pd.Timestamp]:
    all_dates = sorted(set(d for s in data for d in data[s].index))
    available = [d for d in all_dates if d >= date]
    if not available:
        return []
    return available[:ahead + 1]


def build_horizon_results(
    data: dict[str, pd.DataFrame],
    sig: pd.DataFrame,
    entry_date: pd.Timestamp,
    horizons: list[int],
) -> dict:
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


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run backtest on any universe")
    parser.add_argument("--universe", "-u", default="nifty50", help="Universe slug or path to JSON")
    parser.add_argument("--capital", type=float, default=CAPITAL, help="Starting capital")
    parser.add_argument("--horizons", nargs="+", type=int, default=[5, 10, 21], help="Horizons in trading days")
    parser.add_argument("--years", type=int, default=3, help="Years of data")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite DB path")
    args = parser.parse_args()
    results = run_backtest(args.universe, years=args.years, capital=args.capital, horizons=args.horizons, db_path=args.db)
    print_report(results, BacktestConfig(capital=args.capital, horizons=args.horizons, years=args.years))


if __name__ == "__main__":
    main()
