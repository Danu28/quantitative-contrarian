from __future__ import annotations

import pandas as pd
import numpy as np

from src.factors import get_factor_names, generate_factor_signals


def make_data(n_stocks=5, n_dates=60):
    dates = pd.date_range("2024-01-01", periods=n_dates, freq="B")
    data = {}
    for i in range(n_stocks):
        np.random.seed(42 + i)
        close = 100 + np.cumsum(np.random.randn(n_dates) * 0.5)
        close = np.abs(close) + 10
        data[f"STOCK{i}.NS"] = pd.DataFrame({
            "open": close * 0.99, "high": close * 1.02,
            "low": close * 0.98, "close": close,
        }, index=dates)
    return data


class TestGetFactorNames:
    def test_returns_list_of_strings(self):
        names = get_factor_names()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)

    def test_returns_two_names(self):
        names = get_factor_names()
        assert len(names) == 2
        assert "ret_20d" in names
        assert "volatility_20d" in names


class TestGenerateFactorSignals:
    def test_returns_dataframe(self):
        data = make_data()
        sig = generate_factor_signals(data, pd.Timestamp("2024-03-01"))
        assert isinstance(sig, pd.DataFrame)

    def test_has_expected_columns(self):
        data = make_data()
        sig = generate_factor_signals(data, pd.Timestamp("2024-03-01"))
        assert list(sig.columns) == ["symbol", "conviction", "close", "rank"]

    def test_returns_all_stocks_with_sufficient_data(self):
        data = make_data(n_stocks=10, n_dates=60)
        sig = generate_factor_signals(data, pd.Timestamp("2024-03-01"))
        assert len(sig) == 10

    def test_sorted_by_conviction_descending(self):
        data = make_data()
        sig = generate_factor_signals(data, pd.Timestamp("2024-03-01"))
        assert (sig["conviction"].diff().dropna() <= 0).all()

    def test_conviction_is_rank_ret_minus_rank_vol(self):
        data = make_data(n_stocks=10, n_dates=60)
        date = pd.Timestamp("2024-03-01")
        sig = generate_factor_signals(data, date)
        rets, vols = [], []
        for sym, df in data.items():
            idx = df.index.get_loc(date)
            r = df["close"].iloc[idx] / df["close"].iloc[idx - 20] - 1
            dr = df["close"].pct_change()
            v = dr.iloc[idx - 19:idx + 1].std()
            rets.append(r)
            vols.append(v)
        expected = pd.DataFrame({"ret": rets, "vol": vols}).dropna()
        expected["ret_r"] = expected["ret"].rank(pct=True)
        expected["vol_r"] = expected["vol"].rank(pct=True)
        expected["conv"] = expected["ret_r"] - expected["vol_r"]
        expected = expected.sort_values("conv", ascending=False).reset_index(drop=True)
        assert np.allclose(sig["conviction"].values, expected["conv"].values)

    def test_returns_empty_for_insufficient_history(self):
        data = make_data(n_dates=15)  # only 15 days, not enough for 20d lookback
        sig = generate_factor_signals(data, data[list(data.keys())[0]].index[-1])
        assert sig.empty

    def test_handles_missing_symbols(self):
        data = make_data()
        date = pd.Timestamp("2024-03-01")
        data["NEW.NS"] = pd.DataFrame({
            "open": [100], "high": [102], "low": [98], "close": [101],
        }, index=[date])
        sig = generate_factor_signals(data, date)
        assert "NEW.NS" not in sig["symbol"].values

    def test_rank_is_sequential(self):
        data = make_data(n_stocks=8)
        sig = generate_factor_signals(data, pd.Timestamp("2024-03-01"))
        assert list(sig["rank"]) == list(range(1, len(sig) + 1))
