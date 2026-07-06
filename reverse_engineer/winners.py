import pandas as pd
import numpy as np
from pathlib import Path
from data import fetch_nifty_50_data, fetch_index_data
from constituents import get_nifty_50_symbols

DATA_DIR = Path(__file__).parent.parent / "data"


def load_all_data() -> dict[str, pd.DataFrame]:
    return fetch_nifty_50_data()


def compute_forward_returns(price_df: pd.DataFrame, horizon: int = 20) -> pd.Series:
    close = price_df["close"]
    fwd_returns = close.shift(-horizon) / close - 1
    return fwd_returns


def identify_winners(
    data: dict[str, pd.DataFrame],
    horizon: int = 20,
    top_frac: float = 0.1,
) -> pd.DataFrame:
    all_returns = []
    for symbol, df in data.items():
        fwd = compute_forward_returns(df, horizon)
        temp = pd.DataFrame({"symbol": symbol, "fwd_return": fwd, "date": df.index})
        all_returns.append(temp)

    combined = pd.concat(all_returns).dropna()
    results = []
    for date, group in combined.groupby("date"):
        n_winners = max(1, int(len(group) * top_frac))
        group = group.sort_values("fwd_return", ascending=False)
        group["is_winner"] = False
        group.iloc[:n_winners, group.columns.get_loc("is_winner")] = True
        results.append(group)

    return pd.concat(results)


def get_pre_move_data(
    data: dict[str, pd.DataFrame],
    winners: pd.DataFrame,
    pre_move_window: int = 20,
) -> dict:
    instances = {}
    for _, row in winners.iterrows():
        symbol = row["symbol"]
        date = row["date"]
        if symbol not in data:
            continue
        df = data[symbol]
        idx = df.index.get_loc(date)
        start = max(0, idx - pre_move_window)
        pre_move = df.iloc[start:idx]
        instances[(symbol, date)] = {
            "symbol": symbol,
            "winner_date": date,
            "is_winner": row["is_winner"],
            "fwd_return": row["fwd_return"],
            "pre_move_data": pre_move,
        }
    return instances


if __name__ == "__main__":
    print("Loading data...")
    data = load_all_data()
    print(f"Loaded {len(data)} stocks")

    print("Identifying winners (top 10% by 20-day forward return)...")
    winners = identify_winners(data, horizon=20, top_frac=0.1)
    n_winners = winners["is_winner"].sum()
    n_total = len(winners)
    print(f"Total observations: {n_total}, Winner instances: {n_winners} ({100*n_winners/n_total:.1f}%)")

    print("Extracting pre-move windows...")
    instances = get_pre_move_data(data, winners, pre_move_window=20)
    print(f"Pre-move instances extracted: {len(instances)}")
