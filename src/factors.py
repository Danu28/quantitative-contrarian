from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.features import compute_stock_characteristics, get_characteristic_names

_FEATURE_CACHE: list[str] | None = None


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def compute_expanded_features(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    base = compute_stock_characteristics(df, window)
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df.get("volume", pd.Series(0, index=df.index))
    daily_ret = close.pct_change()
    mp = max(3, window // 2)

    f = pd.DataFrame(index=df.index)

    # Additional return horizons
    for d in [10, 15, 20, 60]:
        if d <= len(df) * 0.5:  # only if enough data
            f[f"ret_{d}d"] = close / close.shift(min(d, len(df) - 1)) - 1

    # Additional volatility windows
    for d in [10, 20, 60]:
        if d <= len(df) * 0.5:
            f[f"volatility_{d}d"] = daily_ret.rolling(min(d, len(df) - 1), min_periods=mp).std()

    # Additional MA distances
    for d in [50, 200]:
        if d <= len(df) * 0.5:
            ma = close.rolling(min(d, len(df) - 1), min_periods=mp).mean()
            f[f"price_vs_ma{d}"] = close / ma.replace(0, np.nan)

    # Additional MA slopes
    for d in [20]:
        if d <= len(df) * 0.5:
            ma = close.rolling(min(d, len(df) - 1), min_periods=mp).mean()
            f[f"ma_slope_{d}"] = ma / ma.shift(d) - 1

    # Price range features
    f["high_low_ratio"] = high / low.replace(0, np.nan)
    f["close_open_ratio"] = close / df["open"].replace(0, np.nan)
    daily_range = (high - low) / df["open"].replace(0, np.nan)
    f["daily_range_pct"] = daily_range

    # Volatility ratios
    for n1, n2 in [(5, 20), (10, 60)]:
        if n2 <= len(df) * 0.5:
            v1 = daily_ret.rolling(min(n1, len(df) - 1), min_periods=max(3, n1 // 2)).std()
            v2 = daily_ret.rolling(min(n2, len(df) - 1), min_periods=max(3, n2 // 2)).std()
            f[f"vol_ratio_{n1}_{n2}"] = v1 / v2.replace(0, np.nan)

    # Volume features beyond base
    if (volume > 0).any():
        for d in [20, 50]:
            if d <= len(df) * 0.5:
                vma = volume.rolling(min(d, len(df) - 1), min_periods=mp).mean()
                f[f"volume_vs_ma{d}"] = volume / vma.replace(0, np.nan)
                f[f"volume_slope_{d}"] = vma / vma.shift(min(d, len(df) - 1)) - 1
        v_std = volume.rolling(window, min_periods=mp).std()
        v_mean = volume.rolling(window, min_periods=mp).mean()
        f["volume_volatility"] = v_std / v_mean.replace(0, np.nan)
        f["volume_z_score"] = (volume - v_mean) / v_std.replace(0, np.nan)

    # Lagged returns
    for lag in [1, 2, 5]:
        if lag < len(df):
            f[f"ret_1d_lag{lag}"] = daily_ret.shift(lag)

    # Lagged volatility
    for lag in [1, 5]:
        if lag < len(df):
            v = daily_ret.rolling(window, min_periods=mp).std()
            f[f"volatility_lag{lag}"] = v.shift(lag)

    # Technical indicators
    f["rsi_14"] = _rsi(close, 14)
    highest = high.rolling(14, min_periods=7).max()
    lowest = low.rolling(14, min_periods=7).min()
    f["williams_r"] = (highest - close) / (highest - lowest).replace(0, np.nan) * -100

    # MA crossovers
    for fast, slow in [(5, 10), (10, 20)]:
        if slow <= len(df) * 0.5:
            ma_f = close.rolling(fast, min_periods=max(3, fast // 2)).mean()
            ma_s = close.rolling(min(slow, len(df) - 1), min_periods=max(3, slow // 2)).mean()
            f[f"ma_cross_{fast}_{slow}"] = ma_f / ma_s.replace(0, np.nan) - 1

    # Binary indicators
    for ma_period in [10, 20]:
        col = f"price_vs_ma{ma_period}"
        if col in f.columns:
            f[f"close_above_ma{ma_period}"] = (f[col] > 1).astype(float)
        elif f"price_vs_ma{ma_period}" in base.columns:
            f[f"close_above_ma{ma_period}"] = (base[f"price_vs_ma{ma_period}"] > 1).astype(float)

    # Rolling serial correlation at longer lags
    def _rolling_autocorr(series, lag, w):
        def _acf(arr):
            if len(arr) < lag + 3:
                return np.nan
            return np.corrcoef(arr[:-lag], arr[lag:])[0, 1]
        return series.rolling(w, min_periods=lag + 3).apply(_acf, raw=True)

    for lag in [3, 5]:
        f[f"serial_corr_{lag}"] = _rolling_autocorr(daily_ret, lag, window)

    # Combine with base features (base takes priority for existing names)
    for col in base.columns:
        if col not in f.columns:
            f[col] = base[col]

    return f


def get_factor_names() -> list[str]:
    global _FEATURE_CACHE
    if _FEATURE_CACHE is None:
        _FEATURE_CACHE = sorted(set(get_characteristic_names()) | {
            "ret_10d", "ret_15d", "ret_20d", "ret_60d",
            "volatility_10d", "volatility_20d", "volatility_60d",
            "price_vs_ma50", "price_vs_ma200",
            "ma_slope_20",
            "high_low_ratio", "close_open_ratio", "daily_range_pct",
            "vol_ratio_5_20", "vol_ratio_10_60",
            "volume_vs_ma20", "volume_vs_ma50",
            "volume_slope_20", "volume_slope_50",
            "volume_volatility", "volume_z_score",
            "ret_1d_lag1", "ret_1d_lag2", "ret_1d_lag5",
            "volatility_lag1", "volatility_lag5",
            "rsi_14", "williams_r",
            "ma_cross_5_10", "ma_cross_10_20",
            "close_above_ma10", "close_above_ma20",
            "serial_corr_3", "serial_corr_5",
        })
    return _FEATURE_CACHE


def compute_ic(
    factor_df: pd.DataFrame,
    forward_returns: pd.Series,
    method: str = "spearman",
) -> pd.Series:
    ics = {}
    for col in factor_df.columns:
        x = factor_df[col].dropna()
        y = forward_returns.loc[x.index].dropna()
        both = x.loc[y.index]
        y = y.loc[both.index]
        if len(both) < 30:
            ics[col] = np.nan
            continue
        if method == "spearman":
            r, _ = spearmanr(both, y)
            ics[col] = r
        else:
            ics[col] = both.corr(y)
    return pd.Series(ics).dropna()


def compute_rank_ic(
    factor_df: pd.DataFrame,
    forward_returns: pd.Series,
) -> pd.Series:
    fwd_rank = forward_returns.rank(pct=True)
    return compute_ic(factor_df, fwd_rank, method="spearman")


def compute_ic_decay(
    factor_df: pd.DataFrame,
    close: pd.Series,
    max_lag: int = 20,
    step: int = 5,
) -> pd.DataFrame:
    periods = list(range(step, max_lag + 1, step))
    results = {}
    for p in periods:
        fwd = close.shift(-p) / close - 1
        ics = compute_ic(factor_df, fwd)
        results[p] = ics
    return pd.DataFrame(results)


def filter_correlated(
    ics: pd.Series,
    factor_df: pd.DataFrame,
    threshold: float = 0.8,
    max_features: int = 20,
) -> list[str]:
    ranked = ics.abs().sort_values(ascending=False)
    selected: list[str] = []
    for feat in ranked.index:
        if len(selected) >= max_features:
            break
        if feat not in factor_df.columns:
            continue
        if not selected:
            selected.append(feat)
            continue
        sub = factor_df[selected + [feat]].dropna()
        if sub.empty:
            continue
        corr = sub.corr(method="spearman").iloc[-1, :-1].abs().max()
        if corr < threshold:
            selected.append(feat)
    return selected


def build_factor_composite(
    factor_df: pd.DataFrame,
    feature_weights: dict[str, float],
) -> pd.Series:
    ranks = pd.DataFrame(index=factor_df.index)
    for feat, w in feature_weights.items():
        if feat not in factor_df.columns:
            continue
        col = factor_df[feat].fillna(factor_df[feat].median())
        ranks[feat] = col.rank(pct=True) * w
    if ranks.empty:
        return pd.Series(0, index=factor_df.index)
    total = ranks.sum(axis=1)
    total_w = sum(abs(w) for w in feature_weights.values())
    return total / total_w if total_w > 0 else total


def _daily_cross_section_ics(
    factor_df: pd.DataFrame,
    fwd_col: str = "_fwd",
) -> pd.DataFrame:
    pool = factor_df.copy()
    if fwd_col not in pool.columns:
        pool[fwd_col] = np.nan
    daily_ics: dict[pd.Timestamp, pd.Series] = {}
    for date, group in pool.groupby("date"):
        features = group[[c for c in get_factor_names() if c in group.columns]]
        fwd = group[fwd_col]
        if len(features) < 10:
            continue
        try:
            ics = compute_ic(features, fwd)
            if not ics.empty:
                daily_ics[pd.Timestamp(date)] = ics
        except Exception:
            continue
    if not daily_ics:
        return pd.DataFrame()
    return pd.DataFrame(daily_ics).T.sort_index()


def walk_forward_ic(
    factor_df: pd.DataFrame,
    forward_returns: pd.Series,
    n_windows: int = 5,
    train_frac: float = 0.6,
    min_features: int = 5,
    corr_threshold: float = 0.8,
    max_features: int = 20,
) -> dict:
    all_dates = sorted(factor_df["date"].unique())
    if len(all_dates) < 50:
        return {"status": "insufficient_data", "n_dates": len(all_dates)}

    window_size = int(len(all_dates) * (1 - train_frac) / n_windows)
    if window_size < 10:
        return {"status": "window_too_small", "window_size": window_size}

    train_size = int(len(all_dates) * train_frac)
    results = []

    for i in range(n_windows):
        train_end = train_size + i * window_size
        test_end = train_end + window_size
        if test_end > len(all_dates):
            break

        train_cutoff = all_dates[train_end]
        test_cutoff = all_dates[test_end] if test_end < len(all_dates) else all_dates[-1]
        train_start = all_dates[0]

        train = factor_df[(factor_df["date"] >= train_start) & (factor_df["date"] < train_cutoff)]
        test = factor_df[(factor_df["date"] >= train_cutoff) & (factor_df["date"] <= test_cutoff)]

        if len(train) < 100 or len(test) < 50:
            break

        train_factors = train[[c for c in get_factor_names() if c in train.columns]]
        train_fwd = train["fwd_return"]

        train_ics = compute_ic(train_factors, train_fwd)
        selected = filter_correlated(
            train_ics, train_factors,
            threshold=corr_threshold, max_features=max_features,
        )
        if len(selected) < min_features:
            selected = train_ics.abs().sort_values(ascending=False).head(min_features).index.tolist()

        weights = {f: train_ics.get(f, 0) for f in selected}
        test_factors = test[[c for c in get_factor_names() if c in test.columns]]
        test_fwd = test["fwd_return"]
        test_composite = build_factor_composite(test_factors, weights)

        valid = pd.concat([test_composite, test_fwd], axis=1).dropna()
        if len(valid) < 30:
            continue

        if valid.iloc[:, 0].nunique() < 2 or valid.iloc[:, 1].nunique() < 2:
            continue

        test_ic, test_p = spearmanr(valid.iloc[:, 0], valid.iloc[:, 1])

        results.append({
            "window": i,
            "train_start": str(train["date"].min().date()),
            "train_end": str(train["date"].max().date()),
            "test_start": str(test["date"].min().date()),
            "test_end": str(test["date"].max().date()),
            "n_features": len(selected),
            "train_n": len(train),
            "test_n": len(test),
            "test_ic": float(test_ic) if not np.isnan(test_ic) else None,
            "test_p_value": float(test_p) if not np.isnan(test_p) else None,
            "features": selected,
        })

    if not results:
        return {"status": "no_results"}

    test_ics = [r["test_ic"] for r in results if r.get("test_ic") is not None]

    return {
        "status": "ok",
        "n_windows": len(results),
        "mean_test_ic": float(np.mean(test_ics)) if test_ics else 0,
        "std_test_ic": float(np.std(test_ics)) if len(test_ics) > 1 else 0,
        "ic_stability": float(np.mean(np.array(test_ics) > 0)) if test_ics else 0,
        "mean_n_features": float(np.mean([r["n_features"] for r in results])),
        "windows": results,
    }


def compute_cross_sectional_factors(
    all_data: dict[str, pd.DataFrame],
    window: int = 20,
) -> dict[str, pd.DataFrame]:
    expanded = {}
    for sym, df in all_data.items():
        expanded[sym] = compute_expanded_features(df, window)
    return expanded


def extract_factor_snapshot(
    all_factor_data: dict[str, pd.DataFrame],
    observations: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for _, row in observations.iterrows():
        sym = row["symbol"]
        date = row["date"]
        if sym not in all_factor_data:
            continue
        fd = all_factor_data[sym]
        try:
            vals = fd.loc[date].to_dict()
        except KeyError:
            continue
        if pd.isna(vals.get("volatility")):
            continue
        vals["symbol"] = sym
        vals["date"] = date
        vals["fwd_return"] = row.get("fwd_return", np.nan)
        rows.append(vals)
    return pd.DataFrame(rows)


def run_factor_research(
    universe_slug_or_path: str,
    years: int = 3,
    horizon: int = 5,
    window: int = 20,
    db_path=None,
) -> dict:
    from src.db import DB_PATH, load_symbol_data
    db_path = db_path or DB_PATH

    print(f"{'='*70}")
    print(f"FACTOR RESEARCH: {universe_slug_or_path}")
    print(f"{'='*70}")
    print(f"Horizon: {horizon}d | Window: {window}d | Data: {years}y")

    print("\nLoading data...")
    data = load_symbol_data(universe_slug_or_path, years=years, db_path=db_path)
    print(f"Loaded {len(data)} stocks")

    print(f"Computing expanded features ({len(get_factor_names())} features)...")
    factor_data = compute_cross_sectional_factors(data, window=window)

    print(f"Computing {horizon}-day forward returns...")
    all_rows = []
    for sym, df in data.items():
        close = df["close"]
        fwd = close.shift(-horizon) / close - 1
        temp = pd.DataFrame({
            "symbol": sym, "date": df.index.values, "fwd_return": fwd.values,
        })
        all_rows.append(temp)

    combined = pd.concat(all_rows).dropna(subset=["fwd_return"])
    print(f"Total observations: {len(combined)}")

    print("Extracting factor snapshots...")
    factor_df = extract_factor_snapshot(factor_data, combined)
    for col in factor_df.select_dtypes(include=[np.number]).columns:
        factor_df[col] = factor_df[col].replace([np.inf, -np.inf], np.nan)
    print(f"Total factor instances: {len(factor_df)}")

    print("\nComputing Information Coefficients...")
    all_ics = {}
    for date, group in factor_df.groupby("date"):
        if len(group) < 10:
            continue
        features = group[[c for c in get_factor_names() if c in group.columns]]
        fwd = group["fwd_return"]
        if features.empty:
            continue
        try:
            ics = compute_ic(features, fwd)
            all_ics[date] = ics
        except Exception:
            continue

    ic_df = pd.DataFrame(all_ics).T
    if ic_df.empty:
        print("ERROR: No IC data computed.")
        return {"status": "no_ic_data"}

    mean_ic = ic_df.mean().sort_values(ascending=False)
    ic_stability = (ic_df > 0).mean().sort_values(ascending=False)

    print("\n--- Top 15 Features by Mean IC ---")
    for feat in mean_ic.head(15).index:
        print(f"  {feat:<25s}  IC: {mean_ic[feat]:+.4f}  Stability: {ic_stability[feat]:.1%}")

    print("\n--- Bottom 5 Features by Mean IC ---")
    for feat in mean_ic.tail(5).index:
        print(f"  {feat:<25s}  IC: {mean_ic[feat]:+.4f}  Stability: {ic_stability[feat]:.1%}")

    print("\nIC distribution across features:")
    print(f"  Mean: {mean_ic.mean():+.4f}")
    print(f"  Std:  {mean_ic.std():.4f}")
    print(f"  Max:  {mean_ic.max():+.4f}")
    print(f"  Min:  {mean_ic.min():+.4f}")
    n_positive = (mean_ic > 0).sum()
    print(f"  Positive: {n_positive}/{len(mean_ic)} ({100*n_positive/len(mean_ic):.1f}%)")

    print("\nRunning walk-forward validation (cross-sectional IC)...")
    wf = walk_forward_ic(factor_df, factor_df["fwd_return"], n_windows=5)

    if wf.get("status") == "ok":
        print(f"  Windows: {wf['n_windows']}")
        print(f"  Mean Test IC:  {wf['mean_test_ic']:.4f}")
        print(f"  Test IC Std:   {wf['std_test_ic']:.4f}")
        print(f"  IC Stability:  {wf['ic_stability']:.1%}")
        print(f"  Avg Features:  {wf['mean_n_features']:.0f}")
        for w in wf["windows"]:
            sig = "***" if w.get("test_p_value", 1) < 0.05 else ""
            print(f"    [{w['window']}] Test IC={w['test_ic']:.4f} (p={w.get('test_p_value', 1):.4f}){sig} "
                  f"Features={w['n_features']} Test N={w['test_n']}")

    print(f"\n{'='*70}")
    print("FACTOR RESEARCH COMPLETE")
    print(f"{'='*70}")

    return {
        "status": "ok",
        "ic_by_feature": mean_ic.to_dict(),
        "ic_stability": ic_stability.to_dict(),
        "walk_forward": wf,
        "n_observations": len(factor_df),
    }


def train_factor_weights(
    factor_df: pd.DataFrame,
    corr_threshold: float = 0.8,
    max_features: int = 20,
    min_features: int = 5,
) -> tuple[dict[str, float], list[str]]:
    features = factor_df[[c for c in get_factor_names() if c in factor_df.columns]]
    fwd = factor_df["fwd_return"]
    ics = compute_ic(features, fwd)
    selected = filter_correlated(ics, features, threshold=corr_threshold, max_features=max_features)
    if len(selected) < min_features:
        selected = ics.abs().sort_values(ascending=False).head(min_features).index.tolist()
    weights = {f: ics.get(f, 0) for f in selected}
    return weights, selected


def generate_factor_signals(
    data: dict[str, pd.DataFrame],
    factor_data: dict[str, pd.DataFrame],
    date: pd.Timestamp,
    weights: dict[str, float],
) -> pd.DataFrame:
    feature_names = [f for f in weights if f in next(iter(factor_data.values())).columns]
    if not feature_names:
        return pd.DataFrame()
    common = [f for f in feature_names if all(f in factor_data[s].columns for s in factor_data if date in factor_data[s].index)]
    if not common:
        return pd.DataFrame()
    rows = []
    for sym in factor_data:
        if sym not in data or date not in data[sym].index or date not in factor_data[sym].index:
            continue
        rows.append({"symbol": sym, "close": data[sym].loc[date, "close"],
                     **{f: factor_data[sym].loc[date, f] for f in common}})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("symbol")
    feat_df = df[common].apply(pd.to_numeric, errors="coerce")
    feat_df = feat_df.replace([np.inf, -np.inf], np.nan)
    ranked = feat_df.rank(pct=True)
    score = sum(ranked[feat] * w for feat, w in weights.items()) / sum(abs(w) for w in weights.values())
    result = pd.DataFrame({"symbol": score.index, "conviction": score.values,
                           "close": df.loc[score.index, "close"].values})
    result = result.sort_values("conviction", ascending=False).reset_index(drop=True)
    result["rank"] = range(1, len(result) + 1)
    return result


def run_factor_backtest(
    universe_slug_or_path: str,
    years: int = 3,
    capital: float = 10_000_000,
    max_positions: int = 3,
    hold_days: int = 5,
    hard_stop: float = -0.08,
    db_path=None,
    bear_skip: bool = True,
) -> dict:
    from src.db import DB_PATH, load_data, load_symbol_data

    db_path = db_path or DB_PATH
    print(f"{'='*70}")
    print(f"FACTOR BACKTEST: {universe_slug_or_path}")
    print(f"{'='*70}")
    print(f"Hold: {hold_days}d | Max Pos: {max_positions} | Capital: INR {capital:,.0f}")
    print(f"Bear skip: {bear_skip}")

    print("\nLoading data...")
    df_all = load_data(universe_slug_or_path, db_path=db_path)
    if years:
        cutoff = pd.Timestamp.now() - pd.DateOffset(days=365 * years)
        df_all = df_all[df_all["date"] >= cutoff]
    data = load_symbol_data(universe_slug_or_path, years=years, db_path=db_path, df_all=df_all)

    min_date = df_all["date"].min()
    max_date = df_all["date"].max()
    expected_days = (max_date - min_date).days
    before = len(data)
    data = {
        s: df for s, df in data.items()
        if (df.index.max() - df.index.min()).days >= expected_days * 0.9
    }
    dropped = before - len(data)
    if dropped:
        print(f"  Data quality filter: dropped {dropped} stock(s)")
    print(f"Loaded {len(data)} stocks.")

    print("Computing factor features...")
    factor_data = compute_cross_sectional_factors(data)
    print("Done.")

    print("Training factor weights from full sample...")
    all_rows = []
    for sym, df in data.items():
        close = df["close"]
        fwd = close.shift(-hold_days) / close - 1
        temp = pd.DataFrame({
            "symbol": sym, "date": df.index.values, "fwd_return": fwd.values,
        })
        all_rows.append(temp)
    combined = pd.concat(all_rows).dropna(subset=["fwd_return"])
    factor_df = extract_factor_snapshot(factor_data, combined)
    for col in factor_df.select_dtypes(include=[np.number]).columns:
        factor_df[col] = factor_df[col].replace([np.inf, -np.inf], np.nan)
    weights, selected = train_factor_weights(factor_df)
    print(f"  Selected {len(selected)} features: {selected[:5]}...")
    print(f"  Weight range: {min(weights.values()):.4f} to {max(weights.values()):.4f}")

    try:
        import yfinance as yf
        index_df = yf.download("^NSEI", period=f"{years}y", progress=False, auto_adjust=True)
        index_df.index = pd.to_datetime(index_df.index).tz_localize(None)
        if isinstance(index_df.columns, pd.MultiIndex):
            index_df.columns = [c[0].lower() for c in index_df.columns]
        else:
            index_df.columns = [str(c).lower() for c in index_df.columns]
        index_close = index_df["close"]
        index_ret_20d = index_close / index_close.shift(20) - 1
    except Exception:
        index_ret_20d = pd.Series(dtype=float)
        bear_skip = False

    print("\nRunning backtest...")
    all_dates = sorted(set(d for s in factor_data for d in factor_data[s].index))
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=365 * years)
    all_dates = [d for d in all_dates if d >= cutoff]
    fridays = [d for d in all_dates if d.weekday() == 4]

    if not fridays:
        return {"status": "no_fridays"}

    cash = capital
    trades: list[dict] = []
    equity_curve: list[dict] = []
    peak_equity = capital

    slippage = 0.001
    brokerage = 0.0005
    cost_in = 1 + slippage + brokerage
    cost_out = 1 - slippage - brokerage

    def entry_cost(price, shares):
        return shares * price * cost_in

    def exit_value(price, shares):
        return shares * price * cost_out

    for entry_date in fridays:
        if bear_skip and entry_date in index_ret_20d.index:
            ret20 = index_ret_20d.loc[entry_date]
            if not pd.isna(ret20) and ret20 < -0.03:
                continue

        exit_idx = fridays.index(entry_date) + 1
        if exit_idx >= len(fridays):
            break
        exit_date = fridays[exit_idx]

        signals = generate_factor_signals(data, factor_data, entry_date, weights)
        if signals.empty:
            continue

        candidates = signals.head(max_positions)
        cash_per = cash / (len(candidates) + 1)

        for _, row in candidates.iterrows():
            sym = row["symbol"]
            if sym not in data or entry_date not in data[sym].index or exit_date not in data[sym].index:
                continue
            entry_price = data[sym].loc[entry_date, "close"]
            entry_cost_val = entry_cost(entry_price, 1)
            shares = max(1, int(cash_per / entry_cost_val))
            if shares < 1 or cash < shares * entry_cost_val:
                continue
            cash -= shares * entry_cost_val

            exit_price = data[sym].loc[exit_date, "close"]
            pnl_pct = (exit_price * cost_out / (entry_price * cost_in) - 1) * 100

            trades.append({
                "symbol": sym,
                "entry_date": entry_date,
                "exit_date": exit_date,
                "entry_price": round(entry_price, 2),
                "exit_price": round(exit_price, 2),
                "exit_reason": "scheduled",
                "pnl_pct": round(pnl_pct, 2),
                "days_held": (exit_date - entry_date).days,
                "shares": shares,
            })

            cash += shares * exit_price * cost_out

        total_value = cash
        peak_equity = max(peak_equity, total_value)
        equity_curve.append({
            "date": entry_date, "equity": total_value, "cash": cash,
            "positions_value": 0, "num_positions": 0, "daily_pnl_pct": None,
        })

    eq = pd.DataFrame(equity_curve).set_index("date") if equity_curve else pd.DataFrame()
    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()

    from src.backtest import compute_metrics
    metrics = compute_metrics(eq, trades_df, capital)

    print("\nBacktest complete.")
    print(f"  Trades: {metrics.get('total_trades', 0)}")
    print(f"  CAGR: {metrics.get('cagr_pct', 0):.2f}%")
    print(f"  Sharpe: {metrics.get('sharpe', 0):.2f}")
    print(f"  MaxDD: {metrics.get('max_drawdown_pct', 0):.2f}%")
    print(f"  Win Rate: {metrics.get('win_rate_pct', 0):.1f}%")
    print(f"  Profit Factor: {metrics.get('profit_factor', 0):.2f}")

    return {
        "status": "ok",
        "metrics": metrics,
        "trades": trades_df,
        "equity": eq,
        "n_features": len(selected),
        "n_positions": max_positions,
        "hold_days": hold_days,
        "bear_skip": bear_skip,
    }


def live_factor_scan(
    universe_slug_or_path: str = "nifty50",
    db_path=None,
    n_picks: int = 3,
    hold_days: int = 10,
    years: int = 2,
) -> pd.DataFrame:
    from src.db import DB_PATH, load_data, load_symbol_data

    db_path = db_path or DB_PATH
    print(f"Loading data for {universe_slug_or_path}...")
    df_all = load_data(universe_slug_or_path, db_path=db_path)
    cutoff = pd.Timestamp.now() - pd.DateOffset(days=365 * years)
    df_all = df_all[df_all["date"] >= cutoff]
    data = load_symbol_data(universe_slug_or_path, years=years, db_path=db_path, df_all=df_all)

    min_date = df_all["date"].min()
    max_date = df_all["date"].max()
    expected_days = (max_date - min_date).days
    before = len(data)
    data = {
        s: df for s, df in data.items()
        if (df.index.max() - df.index.min()).days >= expected_days * 0.9
    }

    print(f"Computing factor features for {len(data)} stocks...")
    factor_data = compute_cross_sectional_factors(data)

    latest_date = max(d for s in factor_data for d in factor_data[s].index)
    print(f"Latest data date: {latest_date.date()}")

    print(f"Training factor weights...")
    all_rows = []
    for sym, df in data.items():
        close = df["close"]
        fwd = close.shift(-hold_days) / close - 1
        temp = pd.DataFrame({
            "symbol": sym, "date": df.index.values, "fwd_return": fwd.values,
        })
        all_rows.append(temp)
    combined = pd.concat(all_rows).dropna(subset=["fwd_return"])
    factor_df = extract_factor_snapshot(factor_data, combined)
    for col in factor_df.select_dtypes(include=[np.number]).columns:
        factor_df[col] = factor_df[col].replace([np.inf, -np.inf], np.nan)

    weights, selected = train_factor_weights(factor_df)
    print(f"Using {len(selected)} features:\n  {', '.join(selected[:6])}...")

    signals = generate_factor_signals(data, factor_data, latest_date, weights)
    if signals.empty:
        print("No signals generated.")
        return pd.DataFrame()

    signals["entry_price"] = signals["close"]
    result = signals[["symbol", "conviction", "entry_price", "rank"]].head(n_picks)
    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "backtest":
        run_factor_backtest("nifty50", years=3, max_positions=1)
    elif len(sys.argv) > 1 and sys.argv[1] == "scan":
        picks = live_factor_scan("nifty50", n_picks=3)
        if not picks.empty:
            print(f"\n{'='*60}")
            print("TOP PICKS — FACTOR MODEL")
            print(f"{'='*60}")
            print(picks.to_string(index=False))
            buy = picks.iloc[0]
            print(f"\n-> BUY {buy['symbol']} @ ~{buy['entry_price']:.2f}")
            print(f"   next 10 trading days, skip if Nifty 20d ret < -3%")
            print(f"{'='*60}")
    else:
        run_factor_research("nifty50", years=3, horizon=5)
