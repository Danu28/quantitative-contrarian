from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

from src.factors import (
    compute_expanded_features,
    get_factor_names,
    compute_ic,
    filter_correlated,
    build_factor_composite,
    train_factor_weights,
)


@pytest.fixture
def sample_data():
    dates = pd.date_range("2024-01-01", periods=200, freq="B")
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


class TestComputeExpandedFeatures:
    def test_returns_dataframe(self, sample_data):
        result = compute_expanded_features(sample_data)
        assert isinstance(result, pd.DataFrame)

    def test_has_more_columns_than_base(self, sample_data):
        result = compute_expanded_features(sample_data)
        from src.features import get_characteristic_names
        assert len(result.columns) > len(get_characteristic_names())

    def test_includes_all_base_features(self, sample_data):
        result = compute_expanded_features(sample_data)
        from src.features import get_characteristic_names
        for col in get_characteristic_names():
            assert col in result.columns

    def test_rsi_between_0_and_100(self, sample_data):
        result = compute_expanded_features(sample_data)
        rsi = result["rsi_14"].dropna()
        assert (rsi >= 0).all() and (rsi <= 100).all()


class TestGetFactorNames:
    def test_returns_list_of_strings(self):
        names = get_factor_names()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)
        assert len(names) > 30

    def test_includes_base_feature_names(self):
        names = get_factor_names()
        from src.features import get_characteristic_names
        for col in get_characteristic_names():
            assert col in names


class TestComputeIC:
    def test_returns_series(self, sample_data):
        factors = compute_expanded_features(sample_data)
        fwd = sample_data["close"].shift(-5) / sample_data["close"] - 1
        common = factors.index.intersection(fwd.dropna().index)
        ic = compute_ic(factors.loc[common], fwd.loc[common])
        assert isinstance(ic, pd.Series)
        assert len(ic) > 0

    def test_ic_between_minus_one_and_one(self, sample_data):
        factors = compute_expanded_features(sample_data)
        fwd = sample_data["close"].shift(-5) / sample_data["close"] - 1
        common = factors.index.intersection(fwd.dropna().index)
        ic = compute_ic(factors.loc[common], fwd.loc[common])
        assert (ic.abs() <= 1).all()

    def test_returns_nan_for_few_observations(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        fwd = pd.Series([0.1, 0.2, 0.3])
        ic = compute_ic(df, fwd)
        assert ic.empty


class TestFilterCorrelated:
    def test_returns_subset_of_input(self, sample_data):
        factors = compute_expanded_features(sample_data)
        fwd = sample_data["close"].shift(-5) / sample_data["close"] - 1
        common = factors.index.intersection(fwd.dropna().index)
        ics = compute_ic(factors.loc[common], fwd.loc[common])
        selected = filter_correlated(ics, factors.loc[common], threshold=0.9, max_features=5)
        assert len(selected) <= 5
        assert len(selected) >= 1
        for f in selected:
            assert f in ics.index

    def test_respects_max_features(self, sample_data):
        factors = compute_expanded_features(sample_data)
        fwd = sample_data["close"].shift(-5) / sample_data["close"] - 1
        common = factors.index.intersection(fwd.dropna().index)
        ics = compute_ic(factors.loc[common], fwd.loc[common])
        selected = filter_correlated(ics, factors.loc[common], threshold=0.99, max_features=3)
        assert len(selected) <= 3


class TestBuildFactorComposite:
    def test_returns_series(self, sample_data):
        factors = compute_expanded_features(sample_data)
        weights = {"volatility": 1.0, "avg_true_range_pct": 0.5}
        composite = build_factor_composite(factors, weights)
        assert isinstance(composite, pd.Series)
        assert len(composite) == len(factors)

    def test_handles_missing_features(self, sample_data):
        factors = compute_expanded_features(sample_data)
        weights = {"nonexistent_feature": 1.0}
        composite = build_factor_composite(factors, weights)
        assert (composite == 0).all()


class TestTrainFactorWeights:
    def test_returns_weights_and_selected(self, sample_data):
        factors = compute_expanded_features(sample_data)
        fwd = sample_data["close"].shift(-5) / sample_data["close"] - 1
        factor_df = factors.copy()
        factor_df["fwd_return"] = fwd
        factor_df = factor_df.dropna(subset=["fwd_return"])
        weights, selected = train_factor_weights(factor_df, max_features=10)
        assert isinstance(weights, dict)
        assert isinstance(selected, list)
        assert len(weights) == len(selected)
        assert len(selected) <= 10
