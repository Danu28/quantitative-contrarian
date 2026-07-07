from __future__ import annotations

import pandas as pd
import numpy as np


def compute_stock_characteristics(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"] if "volume" in df.columns else pd.Series(0, index=df.index)
    daily_ret = close.pct_change()
    result = pd.DataFrame(index=df.index)

    mp = min(5, window)
    result["return_over_window"] = close / close.shift(window) - 1
    result["ret_1d"] = close / close.shift(1) - 1
    result["ret_3d"] = close / close.shift(3) - 1
    result["ret_5d"] = close / close.shift(5) - 1
    result["max_return"] = close.rolling(window).max() / close.shift(window) - 1
    roll_max = close.rolling(window, min_periods=mp).max()
    roll_max_dd = close / roll_max - 1
    result["max_drawdown"] = roll_max_dd.rolling(window, min_periods=mp).min()
    result["volatility"] = daily_ret.rolling(window, min_periods=mp).std()
    tr_pct = (high - low) / close.shift(1)
    result["avg_true_range_pct"] = tr_pct.rolling(window, min_periods=mp).mean()
    result["price_vs_high"] = close / high.rolling(window, min_periods=mp).max()
    result["price_vs_low"] = close / low.rolling(window, min_periods=mp).min()
    result["price_vs_ma10"] = close / close.rolling(min(10, window), min_periods=min(5, window)).mean()
    result["price_vs_ma20"] = close / close.rolling(min(20, window), min_periods=min(5, window)).mean()

    ma5 = close.rolling(min(5, window), min_periods=min(3, window)).mean()
    ma10 = close.rolling(min(10, window), min_periods=min(5, window)).mean()
    result["ma_slope_5"] = ma5 / ma5.shift(min(5, window)) - 1
    result["ma_slope_10"] = ma10 / ma10.shift(min(5, window)) - 1

    result["skewness"] = daily_ret.rolling(window, min_periods=mp).skew()
    result["kurtosis"] = daily_ret.rolling(window, min_periods=mp).kurt()
    result["up_day_ratio"] = (daily_ret > 0).rolling(window, min_periods=mp).mean()

    pos_ret = daily_ret.where(daily_ret > 0)
    neg_ret = daily_ret.where(daily_ret < 0)
    result["avg_up_day"] = pos_ret.rolling(window, min_periods=mp).mean()
    result["avg_down_day"] = neg_ret.rolling(window, min_periods=mp).mean()

    threshold = 0.02
    result["gap_frequency"] = (daily_ret.abs() > threshold).rolling(window, min_periods=mp).mean()

    def rolling_autocorr(series, lag, w):
        def _autocorr(arr):
            if len(arr) < lag + 2:
                return np.nan
            return np.corrcoef(arr[:-lag], arr[lag:])[0, 1]
        return series.rolling(w, min_periods=lag + 2).apply(_autocorr, raw=True)

    result["serial_corr_1"] = rolling_autocorr(daily_ret, 1, window)
    result["serial_corr_2"] = rolling_autocorr(daily_ret, 2, window)

    if volume.sum() > 0:
        vol_ma5 = volume.rolling(min(5, window), min_periods=min(3, window)).mean()
        vol_ma10 = volume.rolling(min(10, window), min_periods=min(5, window)).mean()
        result["volume_vs_ma5"] = volume / vol_ma5.replace(0, np.nan)
        result["volume_vs_ma10"] = volume / vol_ma10.replace(0, np.nan)
        result["volume_trend_5"] = vol_ma5 / vol_ma5.shift(min(5, window)) - 1
        result["avg_volume"] = volume.rolling(window, min_periods=mp).mean()
        vol_std = volume.rolling(window, min_periods=mp).std()
        vol_mean = volume.rolling(window, min_periods=mp).mean()
        result["volume_coef_var"] = vol_std / vol_mean.replace(0, np.nan)

    half = max(window // 2, 3)
    recent_vol = daily_ret.rolling(half, min_periods=min(3, half)).std()
    early_vol = daily_ret.shift(half).rolling(half, min_periods=min(3, half)).std()
    result["volatility_trend"] = recent_vol / early_vol - 1
    vol_latest = daily_ret.rolling(min(5, window), min_periods=min(3, window)).std()
    vol_window = daily_ret.rolling(window, min_periods=min(5, window)).std()
    result["volatility_contraction"] = vol_latest / vol_window - 1

    return result


def get_characteristic_names() -> list[str]:
    return [
        "return_over_window", "ret_1d", "ret_3d", "ret_5d",
        "max_return", "max_drawdown", "volatility",
        "avg_true_range_pct", "price_vs_high", "price_vs_low",
        "price_vs_ma10", "price_vs_ma20", "ma_slope_5", "ma_slope_10",
        "skewness", "kurtosis", "up_day_ratio", "avg_up_day", "avg_down_day",
        "gap_frequency", "serial_corr_1", "serial_corr_2",
        "volume_vs_ma5", "volume_vs_ma10", "volume_trend_5",
        "avg_volume", "volume_coef_var", "volatility_trend",
        "volatility_contraction",
    ]


def precompute_all_characteristics(
    data: dict[str, pd.DataFrame],
    window: int = 20,
) -> dict[str, pd.DataFrame]:
    result = {}
    for symbol, df in data.items():
        result[symbol] = compute_stock_characteristics(df, window)
    return result


def extract_characteristics(
    all_char_data: dict[str, pd.DataFrame],
    observations: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for _, row in observations.iterrows():
        symbol = row["symbol"]
        date = row["date"]
        if symbol not in all_char_data:
            continue
        char_df = all_char_data[symbol]
        try:
            vals = char_df.loc[date].to_dict()
        except KeyError:
            continue
        if pd.isna(vals.get("volatility")):
            continue
        vals["symbol"] = symbol
        vals["winner_date"] = date
        vals["is_winner"] = bool(row["is_winner"])
        vals["fwd_return"] = row["fwd_return"]
        rows.append(vals)
    return pd.DataFrame(rows)
