import pandas as pd
import numpy as np
from data import fetch_nifty_50_data
from characteristics import precompute_all_characteristics

ENTRY_DRAWDOWN = -0.08
ENTRY_ATR_MULT = 1.0
ENTRY_VOL_MULT = 1.0
ENTRY_VOLUME_RATIO = 1.0
ENTRY_PRICE_VS_LOW = 1.05
ENTRY_GAP_FREQ = 0.05
ENTRY_PRICE_VS_HIGH_MAX = 0.98
HORIZON = 20


def compute_conviction(c: pd.Series) -> float:
    dd = abs(min(c.get("max_drawdown", 0), 0))
    atr_z = (c.get("avg_true_range_pct", 0)) * 10
    vol_z = (c.get("volatility", 0)) * 50
    gap_z = (c.get("gap_frequency", 0)) * 2
    pvl_z = (1.05 - c.get("price_vs_low", 1))
    return dd + atr_z + vol_z + gap_z + pvl_z


def generate_signals(
    data: dict[str, pd.DataFrame],
    char_data: dict[str, pd.DataFrame],
    date: pd.Timestamp,
) -> pd.DataFrame:
    universe_atr = np.median([
        char_data[s].loc[date, "avg_true_range_pct"]
        for s in char_data if date in char_data[s].index
    ])
    universe_vol = np.median([
        char_data[s].loc[date, "volatility"]
        for s in char_data if date in char_data[s].index
    ])
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
        hv = df["high"].rolling(HORIZON, min_periods=5).max()
        pvh = close / hv.loc[date] if date in hv.index else 1

        dd = c.get("max_drawdown", 0)
        atr = c.get("avg_true_range_pct", 0)
        vol = c.get("volatility", 0)
        gap = c.get("gap_frequency", 0)
        pvl = c.get("price_vs_low", 1)
        vma = c.get("volume_vs_ma10", 0)

        ok = True
        ok &= not pd.isna(dd) and dd <= ENTRY_DRAWDOWN
        ok &= not pd.isna(atr) and atr > universe_atr * ENTRY_ATR_MULT
        ok &= not pd.isna(vol) and vol > universe_vol * ENTRY_VOL_MULT
        ok &= not pd.isna(gap) and gap > ENTRY_GAP_FREQ
        ok &= not pd.isna(pvl) and pvl < ENTRY_PRICE_VS_LOW
        ok &= not pd.isna(vma) and vma > ENTRY_VOLUME_RATIO
        ok &= not pd.isna(pvh) and pvh < ENTRY_PRICE_VS_HIGH_MAX

        if ok:
            signals.append({
                "symbol": symbol,
                "close": close,
                "conviction": compute_conviction(c),
                "max_drawdown": dd,
                "avg_true_range_pct": atr,
                "volatility": vol,
                "gap_frequency": gap,
                "price_vs_low": pvl,
                "volume_vs_ma10": vma,
                "price_vs_high": pvh,
            })

    result = pd.DataFrame(signals)
    if not result.empty:
        result = result.sort_values("conviction", ascending=False).reset_index(drop=True)
        result["rank"] = range(1, len(result) + 1)
    return result


def generate_todays_signals() -> pd.DataFrame:
    data = fetch_nifty_50_data(years=3)
    char_data = precompute_all_characteristics(data, window=HORIZON)
    today = pd.Timestamp.now().normalize()
    if today.weekday() >= 5:
        days_back = today.weekday() - 4
        today -= pd.Timedelta(days=days_back)
    return generate_signals(data, char_data, today)


if __name__ == "__main__":
    signals = generate_todays_signals()
    if signals.empty:
        print("No signals generated for today.")
    else:
        print(f"Generated {len(signals)} signals:")
        print(signals[["rank", "symbol", "close", "conviction"]].to_string(index=False))
