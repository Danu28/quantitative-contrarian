from __future__ import annotations

import numpy as np
import pandas as pd

_FEATURE_NAMES = ["ret_20d", "volatility_20d"]


def get_factor_names() -> list[str]:
    return list(_FEATURE_NAMES)


def generate_factor_signals(
    data: dict[str, pd.DataFrame],
    date: pd.Timestamp,
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
        rows.append({
            "symbol": sym,
            "close": close.iloc[idx],
            "ret_20d": ret_20d,
            "volatility_20d": vol_20d,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["ret_20d", "volatility_20d"])
    if df.empty:
        return pd.DataFrame()

    df["ret_rank"] = df["ret_20d"].rank(pct=True)
    df["vol_rank"] = df["volatility_20d"].rank(pct=True)
    df["conviction"] = df["ret_rank"] - df["vol_rank"]
    df = df.sort_values("conviction", ascending=False).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)
    return df[["symbol", "conviction", "close", "rank"]]
