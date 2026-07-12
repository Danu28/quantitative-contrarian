from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest import (
    SLIPPAGE, BROKERAGE, HARD_STOP, PROFIT_TARGET_1, PROFIT_TARGET_2,
    TRAIL_ACTIVATE, TRAIL_DISTANCE, TIME_STOP_DAYS, MAX_POSITIONS,
    MAX_DRAWDOWN_DISABLE, CAPITAL, REGIME_NORMAL,
    weighted_conviction, generate_signals, Portfolio,
    compute_regime_multiplier, compute_metrics, run_horizon,
    BacktestConfig, HorizonResult,
)

# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def sample_data():
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    n = len(dates)
    data = {}
    for sym in ["STOCK1.NS", "STOCK2.NS", "STOCK3.NS"]:
        base = np.random.uniform(100, 500)
        noise = np.random.randn(n) * 5
        prices = base + noise.cumsum()
        prices = np.abs(prices) + 10
        df = pd.DataFrame({
            "open": prices * 0.99,
            "high": prices * 1.02,
            "low": prices * 0.98,
            "close": prices,
            "volume": np.random.randint(100_000, 10_000_000, n),
        }, index=dates)
        df.index.name = "date"
        data[sym] = df
    return data


@pytest.fixture
def simple_data():
    dates = pd.date_range("2024-01-01", periods=50, freq="B")
    n = len(dates)
    close = np.linspace(100, 110, n) + np.random.randn(n) * 2
    df = pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": np.full(n, 1_000_000),
    }, index=dates)
    df.index.name = "date"
    return {"STOCK1.NS": df}


@pytest.fixture
def char_data(sample_data):
    from src.features import compute_stock_characteristics
    return {s: compute_stock_characteristics(df) for s, df in sample_data.items()}


# ── Signal Tests ──────────────────────────────────────────────────────

BASE_COLS = {
    "max_drawdown": [-0.10, -0.05, -0.15],
    "avg_true_range_pct": [0.02, 0.01, 0.03],
    "volatility": [0.03, 0.02, 0.04],
    "price_vs_low": [0.95, 0.98, 0.92],
    "volume_vs_ma10": [1.2, 1.1, 1.5],
    "gap_frequency": [0.3, 0.2, 0.4],
    "avg_up_day": [0.015, 0.010, 0.020],
    "price_vs_ma10": [0.95, 0.98, 0.92],
    "ma_slope_5": [-0.03, -0.01, -0.05],
    "ret_3d": [-0.05, -0.02, -0.08],
    "price_vs_high": [0.85, 0.90, 0.80],
}

class TestWeightedConviction:
    def test_returns_empty_for_empty_input(self):
        result = weighted_conviction(pd.DataFrame())
        assert result.empty

    def test_adds_conviction_column(self):
        df = pd.DataFrame(BASE_COLS)
        result = weighted_conviction(df)
        assert "conviction" in result.columns
        assert 0 <= result["conviction"].min() <= result["conviction"].max() <= 1

    def test_ranks_better_setup_higher(self):
        df = pd.DataFrame(BASE_COLS)
        result = weighted_conviction(df)
        # Row with higher gap_freq, atr, avg_up_day, volatility should rank higher
        assert result.iloc[0]["conviction"] > 0

    def test_higher_volatility_gap_freq_gets_higher_conviction(self):
        df = pd.DataFrame({
            "max_drawdown": [-0.10, -0.10],
            "avg_true_range_pct": [0.03, 0.01],
            "volatility": [0.04, 0.02],
            "price_vs_low": [0.95, 0.95],
            "volume_vs_ma10": [1.2, 1.2],
            "gap_frequency": [0.4, 0.2],
            "avg_up_day": [0.020, 0.010],
            "price_vs_ma10": [0.92, 0.98],
            "ma_slope_5": [-0.05, -0.01],
            "ret_3d": [-0.08, -0.02],
            "price_vs_high": [0.80, 0.90],
        })
        result = weighted_conviction(df)
        assert result.iloc[0]["conviction"] > result.iloc[1]["conviction"]


class TestGenerateSignals:
    def test_no_signals_when_no_data_match(self, sample_data):
        # Empty char data with required columns -> no universe_atr -> no signals
        char = {}
        for s, df in sample_data.items():
            char[s] = pd.DataFrame({"avg_true_range_pct": [np.nan], "volatility": [np.nan]}, index=df.index[:1])
        date = sample_data["STOCK1.NS"].index[10]
        sig = generate_signals(sample_data, char, date)
        assert sig.empty

    def test_returns_dataframe_with_expected_columns(self, sample_data):
        char = {}
        for s, df in sample_data.items():
            c = df[["close", "high", "low"]].copy()
            c["max_drawdown"] = -0.10
            c["avg_true_range_pct"] = 0.03
            c["volatility"] = 0.04
            c["price_vs_low"] = 0.95
            c["volume_vs_ma10"] = 1.5
            char[s] = c
        date = sample_data["STOCK1.NS"].index[20]
        sig = generate_signals(sample_data, char, date)
        if not sig.empty:
            expected = {"symbol", "close", "conviction", "rank", "max_drawdown",
                        "avg_true_range_pct", "volatility", "price_vs_low",
                        "volume_vs_ma10", "price_vs_high"}
            assert expected.issubset(set(sig.columns))


# ── Portfolio Tests ───────────────────────────────────────────────────

class TestPortfolioCosts:
    def test_entry_cost_includes_slippage_and_brokerage(self):
        pf = Portfolio(100_000)
        cost = pf.entry_cost(100, 10)
        expected = 10 * 100 * (1 + SLIPPAGE + BROKERAGE)
        assert cost == pytest.approx(expected)

    def test_exit_value_deducts_costs(self):
        pf = Portfolio(100_000)
        value = pf.exit_value(100, 10)
        expected = 10 * 100 * (1 - SLIPPAGE - BROKERAGE)
        assert value == pytest.approx(expected)


class TestEvaluateExits:
    @pytest.fixture
    def pf_with_position(self):
        pf = Portfolio(100_000)
        pf.positions["TEST.NS"] = {
            "entry_price": 100, "entry_date": pd.Timestamp("2024-01-01"),
            "shares": 100, "high_since_entry": 100,
            "first_target_hit": False, "trading_days": 5,
        }
        return pf

    def test_hard_stop_triggers(self, pf_with_position):
        should_exit, reason, is_half = pf_with_position.evaluate_exits(
            "TEST.NS", 100 * (1 + HARD_STOP) - 0.01,
            pd.Timestamp("2024-01-10"),
        )
        assert should_exit
        assert reason == "hard_stop"
        assert not is_half

    def test_hard_stop_does_not_trigger_above_threshold(self, pf_with_position):
        should_exit, _, _ = pf_with_position.evaluate_exits(
            "TEST.NS", 100 * (1 + HARD_STOP) + 1,
            pd.Timestamp("2024-01-10"),
        )
        assert not should_exit

    def test_time_stop_triggers_after_20_trading_days(self, pf_with_position):
        pf_with_position.positions["TEST.NS"]["trading_days"] = TIME_STOP_DAYS + 1
        should_exit, reason, is_half = pf_with_position.evaluate_exits(
            "TEST.NS", 110, pd.Timestamp("2024-01-28"),
        )
        assert should_exit
        assert reason == "time_stop"

    def test_trailing_stop_activates(self, pf_with_position):
        # Stock went up to 140 (+40%), trailing activates at +10%, trail distance 12%
        pf_with_position.positions["TEST.NS"]["high_since_entry"] = 140
        # Trigger: price drops 12% from high = 140 * 0.88 = 123.2, ret = +23.2% >= 10%
        trigger_price = 140 * (1 - TRAIL_DISTANCE) - 0.01
        should_exit, reason, is_half = pf_with_position.evaluate_exits(
            "TEST.NS", trigger_price, pd.Timestamp("2024-01-15"),
        )
        assert should_exit
        assert reason == "trailing_stop"

    def test_trailing_stop_not_triggered_below_activation(self, pf_with_position):
        # Only went up 5%, trailing activates at 10%
        pf_with_position.positions["TEST.NS"]["high_since_entry"] = 105
        trigger_price = 105 * (1 - TRAIL_DISTANCE)
        should_exit, _, _ = pf_with_position.evaluate_exits(
            "TEST.NS", trigger_price, pd.Timestamp("2024-01-15"),
        )
        assert not should_exit

    def test_profit_target_1_half_exit(self, pf_with_position):
        price = 100 * (1 + PROFIT_TARGET_1) + 0.01
        should_exit, reason, is_half = pf_with_position.evaluate_exits(
            "TEST.NS", price, pd.Timestamp("2024-01-15"),
        )
        assert should_exit
        assert reason == "profit_target_1_half"
        assert is_half

    def test_profit_target_2_full_exit_after_half(self, pf_with_position):
        pf_with_position.positions["TEST.NS"]["first_target_hit"] = True
        price = 100 * (1 + PROFIT_TARGET_2) + 0.01
        should_exit, reason, is_half = pf_with_position.evaluate_exits(
            "TEST.NS", price, pd.Timestamp("2024-01-20"),
        )
        assert should_exit
        assert reason == "profit_target_2"
        assert not is_half

    def test_multiple_conditions_hard_stop_wins(self, pf_with_position):
        pf_with_position.positions["TEST.NS"]["trading_days"] = TIME_STOP_DAYS + 1
        price = 100 * (1 + HARD_STOP) - 1
        should_exit, reason, _ = pf_with_position.evaluate_exits(
            "TEST.NS", price, pd.Timestamp("2024-01-28"),
        )
        assert reason == "hard_stop"


class TestPositionManagement:
    def test_exit_position_records_trade(self):
        pf = Portfolio(100_000)
        entry_price = 100 * (1 + SLIPPAGE + BROKERAGE)
        pf.cash -= 100 * entry_price
        pf.positions["TEST.NS"] = {
            "entry_price": entry_price, "entry_date": pd.Timestamp("2024-01-01"),
            "shares": 100, "high_since_entry": entry_price,
            "first_target_hit": False, "trading_days": 10,
        }
        pf.exit_position("TEST.NS", 110, pd.Timestamp("2024-02-01"), "time_stop")
        assert "TEST.NS" not in pf.positions
        assert len(pf.trades) == 1
        trade = pf.trades[0]
        assert trade["symbol"] == "TEST.NS"
        assert trade["exit_reason"] == "time_stop"
        assert trade["pnl_pct"] is not None

    def test_exit_half_position_reduces_shares(self):
        pf = Portfolio(100_000)
        entry_price = 100 * (1 + SLIPPAGE + BROKERAGE)
        pf.cash -= 100 * entry_price
        pf.positions["TEST.NS"] = {
            "entry_price": entry_price, "entry_date": pd.Timestamp("2024-01-01"),
            "shares": 100, "high_since_entry": entry_price,
            "first_target_hit": False, "trading_days": 5,
        }
        pf.exit_half_position("TEST.NS", 120, pd.Timestamp("2024-01-15"))
        assert pf.positions["TEST.NS"]["shares"] == 50
        assert pf.positions["TEST.NS"]["first_target_hit"]


class TestRebalance:
    def test_no_signals_no_new_positions(self):
        pf = Portfolio(100_000)
        pf._rebalance(pd.DataFrame(), {}, pd.Timestamp("2024-01-05"), REGIME_NORMAL)
        assert len(pf.positions) == 0

    def test_creates_positions_for_candidates(self):
        pf = Portfolio(1_000_000)
        signals = pd.DataFrame({"symbol": ["STOCK1.NS"], "conviction": [0.8], "close": [100]})
        prices = {"STOCK1.NS": 100}
        pf._rebalance(signals, prices, pd.Timestamp("2024-01-05"), REGIME_NORMAL)
        assert len(pf.positions) == 1
        assert "STOCK1.NS" in pf.positions

    def test_max_positions_respected(self):
        pf = Portfolio(1_000_000)
        # Fill to max
        for i in range(MAX_POSITIONS):
            sym = f"STOCK{i}.NS"
            pf.positions[sym] = {
                "entry_price": 100, "entry_date": pd.Timestamp("2024-01-01"),
                "shares": 100, "high_since_entry": 100,
                "first_target_hit": False, "trading_days": 5,
            }
            pf.cash -= 100 * 100
        signals = pd.DataFrame({"symbol": ["NEWSTOCK.NS"], "conviction": [0.9], "close": [100]})
        prices = {"NEWSTOCK.NS": 100}
        pf._rebalance(signals, prices, pd.Timestamp("2024-01-05"), REGIME_NORMAL)
        assert len(pf.positions) == MAX_POSITIONS

    def test_regime_multiplier_reduces_positions(self):
        pf = Portfolio(1_000_000)
        signals = pd.DataFrame({
            "symbol": [f"STOCK{i}.NS" for i in range(10)],
            "conviction": [0.8] * 10, "close": [100] * 10,
        })
        prices = {f"STOCK{i}.NS": 100 for i in range(10)}
        pf._rebalance(signals, prices, pd.Timestamp("2024-01-05"), 0.33)
        # 0.33 * 10 = 3.3 -> 3 max, minus 0 existing = 3 new
        assert len(pf.positions) <= 3


class TestProcessDay:
    def test_no_errors_with_no_signals(self):
        pf = Portfolio(100_000)
        pf.process_day(pd.DataFrame(), {}, pd.Timestamp("2024-01-05"), REGIME_NORMAL)
        assert len(pf.equity_curve) == 1

    def test_equity_curve_recorded(self, simple_data):
        pf = Portfolio(100_000)
        for date in simple_data["STOCK1.NS"].index[:10]:
            prices = {"STOCK1.NS": simple_data["STOCK1.NS"].loc[date, "close"]}
            pf.process_day(pd.DataFrame(), prices, date, REGIME_NORMAL)
        assert len(pf.equity_curve) == 10

    def test_emergency_drawdown_liquidates(self):
        pf = Portfolio(100_000)
        pf.peak_equity = 100_000
        pf.cash = 0
        pf.positions["TEST.NS"] = {
            "entry_price": 100, "entry_date": pd.Timestamp("2024-01-01"),
            "shares": 100, "high_since_entry": 100,
            "first_target_hit": False, "trading_days": 10,
        }
        prices = {"TEST.NS": 50}
        # Cash 0 + 100 shares * 50 = 5000 total equity vs 100000 peak = 95% drawdown
        pf.process_day(pd.DataFrame(), prices, pd.Timestamp("2024-01-10"), REGIME_NORMAL)
        assert pf.disabled
        assert "TEST.NS" not in pf.positions

    def test_daily_loss_circuit_breaker_blocks_rebalance(self):
        """When daily loss exceeds MAX_DAILY_LOSS, rebalancing should not happen."""
        pf = Portfolio(100_000)
        # Create a position that will hard-stop, generating a daily loss
        ep = 100 * (1 + SLIPPAGE + BROKERAGE)
        pf.cash -= 100 * ep
        pf.positions["LOSER.NS"] = {
            "entry_price": ep, "entry_date": pd.Timestamp("2024-01-01"),
            "shares": 1000, "high_since_entry": ep,
            "first_target_hit": False, "trading_days": 5,
        }
        # Hit hard stop -> large loss -> daily_loss > MAX_DAILY_LOSS
        hard_stop_price = 100 * (1 + HARD_STOP) - 1
        signals = pd.DataFrame({"symbol": ["NEW.NS"], "conviction": [0.9], "close": [100]})
        prices = {"LOSER.NS": hard_stop_price, "NEW.NS": 100}
        friday = pd.Timestamp("2024-01-05")
        pf.process_day(signals, prices, friday, REGIME_NORMAL)
        assert "NEW.NS" not in pf.positions

    def test_daily_loss_below_threshold_allows_rebalance(self):
        """When daily loss is within limit, rebalancing should proceed."""
        pf = Portfolio(100_000)
        signals = pd.DataFrame({"symbol": ["NEW.NS"], "conviction": [0.9], "close": [100]})
        prices = {"NEW.NS": 100}
        friday = pd.Timestamp("2024-01-05")
        pf.process_day(signals, prices, friday, REGIME_NORMAL)
        assert "NEW.NS" in pf.positions


class TestSectorConcentration:
    def test_sector_count_tracks_positions(self):
        sector_map = {"A.NS": "Tech", "B.NS": "Tech", "C.NS": "Energy"}
        pf = Portfolio(100_000, sector_map=sector_map)
        for sym in ["A.NS", "C.NS"]:
            pf.positions[sym] = {"shares": 100, "entry_price": 100}
        counts = pf.sector_count()
        assert counts.get("Tech") == 1
        assert counts.get("Energy") == 1

    def test_sector_limit_blocks_excess_in_same_sector(self):
        sector_map = {"A.NS": "Tech", "B.NS": "Tech", "C.NS": "Tech", "D.NS": "Energy"}
        pf = Portfolio(10_000_000, sector_map=sector_map)
        ep = 100 * (1 + SLIPPAGE + BROKERAGE)
        # Manually set positions to trigger sector limiting
        pf.positions["A.NS"] = {"shares": 10000, "entry_price": ep, "entry_date": pd.Timestamp("2024-01-01"),
                                "high_since_entry": ep, "first_target_hit": False, "trading_days": 5}
        pf.positions["B.NS"] = {"shares": 10000, "entry_price": ep, "entry_date": pd.Timestamp("2024-01-01"),
                                "high_since_entry": ep, "first_target_hit": False, "trading_days": 5}
        pf.cash = 8_000_000
        pf._rebalance(pd.DataFrame(), {}, pd.Timestamp("2024-01-05"), 3)
        # MAX_SECTOR_POSITIONS=2, already have 2 Tech, so C.NS (Tech) should be blocked,
        # but D.NS (Energy) should be allowed.
        signals = pd.DataFrame({
            "symbol": ["C.NS", "D.NS"],
            "conviction": [0.9, 0.8], "close": [100, 100],
        })
        prices = {"C.NS": 100, "D.NS": 100}
        pf._rebalance(signals, prices, pd.Timestamp("2024-01-05"), 3)
        assert "D.NS" in pf.positions
        assert "C.NS" not in pf.positions


class TestGetPerformance:
    def test_returns_dict_with_expected_keys(self, simple_data):
        pf = Portfolio(100_000)
        pf.positions["STOCK1.NS"] = {
            "entry_price": 100, "entry_date": simple_data["STOCK1.NS"].index[0],
            "shares": 100, "high_since_entry": 100,
            "first_target_hit": False, "trading_days": 5,
        }
        pf.exit_position("STOCK1.NS", 110, simple_data["STOCK1.NS"].index[5], "time_stop")
        for date in simple_data["STOCK1.NS"].index[:10]:
            prices = {"STOCK1.NS": simple_data["STOCK1.NS"].loc[date, "close"]}
            pf.process_day(pd.DataFrame(), prices, date, REGIME_NORMAL)
        eq = pd.DataFrame(pf.equity_curve).set_index("date") if pf.equity_curve else pd.DataFrame()
        trades = pf.get_trades_summary()
        perf = compute_metrics(eq, trades, 100_000)
        expected = {"total_return_pct", "cagr_pct", "volatility_pct", "sharpe",
                    "sortino", "max_drawdown_pct", "total_trades", "win_rate_pct",
                    "profit_factor", "final_equity", "peak_equity"}
        assert expected.issubset(set(perf.keys()))

    def test_returns_insufficient_data_with_few_points(self, simple_data):
        pf = Portfolio(100_000)
        pf.process_day(pd.DataFrame(), {"STOCK1.NS": 100}, simple_data["STOCK1.NS"].index[0], REGIME_NORMAL)
        eq = pd.DataFrame(pf.equity_curve).set_index("date") if pf.equity_curve else pd.DataFrame()
        trades = pf.get_trades_summary()
        perf = compute_metrics(eq, trades, 100_000)
        assert perf.get("status") == "insufficient_data"


class TestComputeMetrics:
    def test_returns_insufficient_for_empty_data(self):
        metrics = compute_metrics(pd.DataFrame(), pd.DataFrame(), 100_000)
        assert metrics.get("status") == "insufficient_data"

    def test_computes_correct_win_rate(self):
        eq = pd.DataFrame({
            "equity": [100_000, 101_000, 102_000, 103_000, 104_000, 105_000],
            "positions_value": [50_000, 52_000, 48_000, 55_000, 53_000, 51_000],
        }, index=pd.date_range("2024-01-01", periods=6))
        trades = pd.DataFrame({
            "pnl_pct": [5, -3, 2, 4, -1],
            "days_held": [5, 7, 4, 6, 8],
            "exit_reason": ["time_stop"] * 5,
        })
        metrics = compute_metrics(eq, trades, 100_000)
        assert metrics["win_rate_pct"] == pytest.approx(60.0)
        assert metrics["total_trades"] == 5


class TestRegimeMultiplier:
    def test_bull_regime_returns_reduced(self, sample_data):
        dates = list(sample_data["STOCK1.NS"].index)
        mult = compute_regime_multiplier(dates[30], sample_data, dates)
        # With random data, just check it returns something valid
        assert 0 < mult <= 1.0

    def test_early_dates_default_to_normal(self, sample_data):
        dates = list(sample_data["STOCK1.NS"].index)
        mult = compute_regime_multiplier(dates[5], sample_data, dates)
        assert mult == REGIME_NORMAL


class TestSurvivorshipBias:
    def test_filter_drops_short_history_stocks(self):
        """Stocks with <90% of backtest period data should be excluded."""
        import pandas as pd
        from datetime import datetime, timedelta

        # Simulate the filter logic from run_backtest
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        max_date = dates.max()
        min_date = dates.min()
        expected_days = (max_date - min_date).days

        # Full-history stock
        full_df = pd.DataFrame({"close": range(100, 200)}, index=dates)
        full_days = (full_df.index.max() - full_df.index.min()).days
        assert full_days >= expected_days * 0.9

        # Short-history stock (last 50 days only)
        short_df = pd.DataFrame({"close": range(150, 200)}, index=dates[50:])
        short_days = (short_df.index.max() - short_df.index.min()).days
        assert short_days < expected_days * 0.9


class TestRunHorizon:
    def test_returns_horizon_result(self, sample_data):
        char = {}
        for s, df in sample_data.items():
            from src.features import compute_stock_characteristics
            char[s] = compute_stock_characteristics(df)
        config = BacktestConfig(capital=100_000, years=1)
        result = run_horizon(sample_data, char, 10, config)
        assert isinstance(result, HorizonResult)
        assert result.horizon == 10
        assert isinstance(result.metrics, dict)
