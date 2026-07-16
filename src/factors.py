from __future__ import annotations

import numpy as np
import pandas as pd

_FEATURE_NAMES = ["ret_20d", "volatility_20d", "vol_ratio", "sector_rel_ret", "recovery_ratio"]


def get_factor_names() -> list[str]:
    return list(_FEATURE_NAMES)


def generate_factor_signals(
    data: dict[str, pd.DataFrame],
    date: pd.Timestamp,
    sector_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    rows = []
    for sym, df in data.items():
        if date not in df.index:
            continue
        idx = df.index.get_loc(date)
        close = df["close"]
        if idx < 20:
            continue
        ret_20d = close.iloc[idx] / close.iloc[idx - 20] - 1
        daily_ret = close.pct_change()
        vol_20d = daily_ret.iloc[max(0, idx - 19):idx + 1].std()

        vol_ratio = None
        if "volume" in df.columns:
            start_20 = max(0, idx - 19)
            start_60 = max(0, idx - 59)
            vol_20 = df["volume"].iloc[start_20:idx + 1].mean()
            vol_60 = df["volume"].iloc[start_60:idx + 1].mean()
            if vol_60 > 0:
                vol_ratio = vol_20 / vol_60

        low_5d = df["low"].iloc[max(0, idx - 4):idx + 1].min()
        recovery_ratio = close.iloc[idx] / low_5d if low_5d > 0 else 1.0

        rows.append({
            "symbol": sym,
            "close": close.iloc[idx],
            "ret_20d": ret_20d,
            "volatility_20d": vol_20d,
            "vol_ratio": vol_ratio,
            "recovery_ratio": recovery_ratio,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["ret_20d", "volatility_20d"])
    if df.empty:
        return pd.DataFrame()

    df["vol_ratio"] = df["vol_ratio"].fillna(1.0)
    df["ret_vol_adj"] = df["ret_20d"] * df["vol_ratio"] / df["volatility_20d"]
    df["ret_vol_adj_rank"] = df["ret_vol_adj"].rank(pct=True)
    df["recovery_vol_adj"] = df["recovery_ratio"] / df["volatility_20d"]
    df["recovery_rank"] = df["recovery_vol_adj"].rank(pct=True)

    if sector_map:
        df["sector"] = df["symbol"].map(sector_map).fillna("Unknown")
        sector_medians = df.groupby("sector")["ret_20d"].transform("median")
        df["sector_rel_ret"] = df["ret_20d"] - sector_medians
        df["sector_rel_rank"] = df["sector_rel_ret"].rank(pct=True)
        df["conviction"] = df["ret_vol_adj_rank"] + df["sector_rel_rank"] + df["recovery_rank"]
    else:
        df["conviction"] = df["ret_vol_adj_rank"] + df["recovery_rank"]

    df = df.sort_values("conviction", ascending=False).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)
    return df[["symbol", "conviction", "close", "rank"]]
