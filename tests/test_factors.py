from __future__ import annotations

import pandas as pd
import numpy as np

from src.factors import get_factor_names, generate_factor_signals


def make_data(n_stocks=5, n_dates=60, with_volume=False):
    dates = pd.date_range("2024-01-01", periods=n_dates, freq="B")
    data = {}
    for i in range(n_stocks):
        np.random.seed(42 + i)
        close = 100 + np.cumsum(np.random.randn(n_dates) * 0.5)
        close = np.abs(close) + 10
        cols = {"open": close * 0.99, "high": close * 1.02,
                "low": close * 0.98, "close": close}
        if with_volume:
            cols["volume"] = np.random.randint(100000, 10000000, n_dates)
        data[f"STOCK{i}.NS"] = pd.DataFrame(cols, index=dates)
    return data


class TestGetFactorNames:
    def test_returns_list_of_strings(self):
        names = get_factor_names()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)

    def test_returns_five_names(self):
        names = get_factor_names()
        assert len(names) == 5
        assert "ret_20d" in names
        assert "volatility_20d" in names
        assert "vol_ratio" in names
        assert "sector_rel_ret" in names
        assert "recovery_ratio" in names


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

    def test_conviction_formula_without_volume(self):
        data = make_data(n_stocks=10, n_dates=60)
        date = pd.Timestamp("2024-03-01")
        sig = generate_factor_signals(data, date)
        rets, vols, recs = [], [], []
        for sym, df in data.items():
            idx = df.index.get_loc(date)
            r = df["close"].iloc[idx] / df["close"].iloc[idx - 20] - 1
            dr = df["close"].pct_change()
            v = dr.iloc[idx - 19:idx + 1].std()
            low_5d = df["low"].iloc[max(0, idx - 4):idx + 1].min()
            rec = df["close"].iloc[idx] / low_5d if low_5d > 0 else 1.0
            rets.append(r)
            vols.append(v)
            recs.append(rec)
        expected = pd.DataFrame({"ret": rets, "vol": vols, "rec": recs}).dropna()
        # No volume → vol_ratio=1.0 → ret×1.0=ret → ret_vol_rank = Rank(ret)
        expected["ret_r"] = expected["ret"].rank(pct=True)
        expected["vol_r"] = expected["vol"].rank(pct=True)
        expected["rec_adj"] = expected["rec"] / expected["vol"]
        expected["rec_r"] = expected["rec_adj"].rank(pct=True)
        expected["conv"] = expected["ret_r"] + expected["rec_r"] - expected["vol_r"]
        expected = expected.sort_values("conv", ascending=False).reset_index(drop=True)
        assert np.allclose(sig["conviction"].values, expected["conv"].values)

    def test_conviction_with_volume_and_sector(self):
        data = make_data(n_stocks=10, n_dates=120, with_volume=True)
        date = pd.Timestamp("2024-05-01")
        sector_map = {f"STOCK{i}.NS": "Tech" if i < 5 else "Finance" for i in range(10)}
        sig = generate_factor_signals(data, date, sector_map)
        assert not sig.empty
        assert len(sig) == 10
        # All stocks with volume data should have different conviction than baseline
        assert not np.allclose(sig["conviction"], 0.5)

    def test_sector_map_empty_falls_back(self):
        data = make_data(n_stocks=5, n_dates=60)
        date = pd.Timestamp("2024-03-01")
        sig_with = generate_factor_signals(data, date, sector_map={})
        sig_without = generate_factor_signals(data, date)
        assert np.allclose(sig_with["conviction"].values, sig_without["conviction"].values)

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
