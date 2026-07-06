from __future__ import annotations
import pandas as pd
import numpy as np

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

    def evaluate_exits(
        self,
        symbol: str,
        price: float,
        current_date: pd.Timestamp,
    ) -> tuple[bool, str | None, bool]:
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

    def exit_position(
        self,
        symbol: str,
        price: float,
        current_date: pd.Timestamp,
        exit_reason: str,
    ):
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

    def exit_half_position(
        self,
        symbol: str,
        price: float,
        current_date: pd.Timestamp,
    ):
        pos = self.positions.get(symbol)
        if pos is None or pos["first_target_hit"]:
            return
        exit_price = price * (1 - SLIPPAGE - BROKERAGE)
        half_shares = pos["shares"] // 2
        proceeds = half_shares * exit_price
        self.cash += proceeds
        pos["shares"] -= half_shares
        pos["first_target_hit"] = True

    def process_day(
        self,
        signals: pd.DataFrame,
        prices: dict[str, float],
        current_date: pd.Timestamp,
        regime_multiplier: float = REGIME_NORMAL,
    ):
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

        pv = sum(
            prices.get(s, 0) * pos["shares"]
            for s, pos in self.positions.items()
        )
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
            "date": current_date,
            "equity": total,
            "cash": self.cash,
            "positions_value": pv,
            "num_positions": len(self.positions),
            "daily_pnl_pct": None,
        })

        if len(self.equity_curve) >= 2:
            prev_eq = self.equity_curve[-2]["equity"]
            self.equity_curve[-1]["daily_pnl_pct"] = (total / prev_eq - 1) * 100

    MIN_POSITIONS = 3

    def _rebalance(
        self,
        signals: pd.DataFrame,
        prices: dict[str, float],
        current_date: pd.Timestamp,
        regime_multiplier: float,
    ):
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
                    "entry_price": ep,
                    "entry_date": current_date,
                    "shares": shares,
                    "high_since_entry": ep,
                    "first_target_hit": False,
                }

    def get_positions_summary(self) -> pd.DataFrame:
        rows = []
        for symbol, pos in self.positions.items():
            rows.append({
                "symbol": symbol,
                "entry_date": pos["entry_date"],
                "entry_price": pos["entry_price"],
                "shares": pos["shares"],
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
            "total_return_pct": total_ret * 100,
            "cagr_pct": cagr * 100,
            "volatility_pct": vol * 100,
            "sharpe": sharpe,
            "sortino": sortino,
            "max_drawdown_pct": mdd * 100,
            "total_trades": len(trades_df),
            "win_rate_pct": win_rate,
            "profit_factor": profit_factor,
            "final_equity": eq["equity"].iloc[-1],
            "peak_equity": self.peak_equity,
            "num_positions": len(self.positions),
            "disabled": self.disabled,
        }


def run_simulation(
    data: dict[str, pd.DataFrame],
    char_data: dict[str, pd.DataFrame],
    signal_fn,
    horizon: int = 20,
    capital: float = CAPITAL,
) -> Portfolio:
    all_dates = sorted(set(
        d for s in char_data for d in char_data[s].index
    ))
    pf = Portfolio(capital)
    for i, date in enumerate(all_dates):
        if i % 100 == 0:
            print(f"  Sim: {i}/{len(all_dates)}")
        prices = {
            s: data[s].loc[date, "close"]
            for s in data if date in data[s].index
        }
        signals = signal_fn(date)
        pf.process_day(signals, prices, date)
    return pf


if __name__ == "__main__":
    print("Portfolio module loaded. Use via main.py")
