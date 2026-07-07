from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

from src.features import (
    compute_stock_characteristics,
    precompute_all_characteristics,
    get_characteristic_names,
    extract_characteristics,
)


@pytest.fixture
def sample_df():
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    n = len(dates)
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    close = np.abs(close) + 10
    df = pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": np.random.randint(100_000, 10_000_000, n),
    }, index=dates)
    df.index.name = "date"
    return df


class TestComputeStockCharacteristics:
    def test_returns_dataframe(self, sample_df):
        result = compute_stock_characteristics(sample_df)
        assert isinstance(result, pd.DataFrame)

    def test_has_expected_columns(self, sample_df):
        result = compute_stock_characteristics(sample_df)
        expected = set(get_characteristic_names())
        assert expected.issubset(set(result.columns))

    def test_index_matches_input(self, sample_df):
        result = compute_stock_characteristics(sample_df)
        assert list(result.index) == list(sample_df.index)

    def test_max_drawdown_is_negative_or_zero(self, sample_df):
        result = compute_stock_characteristics(sample_df)
        max_dd = result["max_drawdown"].dropna()
        assert (max_dd <= 0).all()

    def test_volatility_is_positive(self, sample_df):
        result = compute_stock_characteristics(sample_df)
        vol = result["volatility"].dropna()
        assert (vol > 0).all()

    def test_price_vs_low_between_1_and_inf(self, sample_df):
        result = compute_stock_characteristics(sample_df)
        pvl = result["price_vs_low"].dropna()
        assert (pvl >= 1.0).all()

    def test_returns_expected_columns_without_volume(self):
        dates = pd.date_range("2024-01-01", periods=50, freq="B")
        df = pd.DataFrame({
            "open": np.linspace(100, 110, 50),
            "high": np.linspace(102, 112, 50),
            "low": np.linspace(98, 108, 50),
            "close": np.linspace(100, 110, 50),
        }, index=dates)
        result = compute_stock_characteristics(df)
        assert "max_drawdown" in result.columns
        assert "volatility" in result.columns


class TestPrecomputeAllCharacteristics:
    def test_returns_dict_with_same_keys(self):
        dates = pd.date_range("2024-01-01", periods=30, freq="B")
        data = {}
        for sym in ["A.NS", "B.NS"]:
            data[sym] = pd.DataFrame({
                "open": np.linspace(100, 110, 30),
                "high": np.linspace(102, 112, 30),
                "low": np.linspace(98, 108, 30),
                "close": np.linspace(100, 110, 30),
                "volume": np.full(30, 1_000_000),
            }, index=dates)
        result = precompute_all_characteristics(data)
        assert set(result.keys()) == {"A.NS", "B.NS"}
        for k in result:
            assert isinstance(result[k], pd.DataFrame)


class TestExtractCharacteristics:
    def test_returns_dataframe(self, sample_df):
        char = {"STOCK.NS": compute_stock_characteristics(sample_df)}
        obs = pd.DataFrame({
            "symbol": ["STOCK.NS", "STOCK.NS"],
            "date": [sample_df.index[20], sample_df.index[30]],
            "is_winner": [True, False],
            "fwd_return": [0.05, -0.03],
        })
        result = extract_characteristics(char, obs)
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0

    def test_filters_missing_symbols(self, sample_df):
        char = {"STOCK.NS": compute_stock_characteristics(sample_df)}
        obs = pd.DataFrame({
            "symbol": ["MISSING.NS"],
            "date": [sample_df.index[20]],
            "is_winner": [True],
            "fwd_return": [0.05],
        })
        result = extract_characteristics(char, obs)
        assert result.empty
