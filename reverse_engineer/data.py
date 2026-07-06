import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from constituents import get_nifty_50_symbols, NIFTY_50_INDEX_TICKER

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def fetch_stock_data(symbol: str, years: int = 10) -> pd.DataFrame:
    cache_path = DATA_DIR / f"{symbol.replace('.', '_')}.parquet"
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        last_date = df.index.max()
        if last_date >= pd.Timestamp.now().normalize() - timedelta(days=1):
            return df
        new = yf.download(symbol, start=last_date + timedelta(days=1), progress=False, auto_adjust=True)
        if not new.empty:
            new.index = pd.to_datetime(new.index)
            if isinstance(new.columns, pd.MultiIndex):
                new.columns = [c[0].lower() for c in new.columns]
            else:
                new.columns = [str(c).lower() for c in new.columns]
            combined = pd.concat([df, new.loc[~new.index.isin(df.index)]])
            combined.to_parquet(cache_path)
            return combined
        return df
    df = yf.download(symbol, start=datetime.now() - timedelta(days=365 * years), progress=False, auto_adjust=True)
    if df.empty:
        return df
    df.index = pd.to_datetime(df.index)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]
    df.to_parquet(cache_path)
    return df


def fetch_nifty_50_data(years: int = 10) -> dict[str, pd.DataFrame]:
    symbols = get_nifty_50_symbols()
    data = {}
    for s in symbols:
        df = fetch_stock_data(s, years)
        if not df.empty:
            data[s] = df
    return data


def fetch_index_data(years: int = 10) -> pd.DataFrame:
    return fetch_stock_data(NIFTY_50_INDEX_TICKER, years)


if __name__ == "__main__":
    print("Fetching NIFTY 50 index data...")
    idx = fetch_index_data()
    print(f"Index: {len(idx)} rows from {idx.index.min().date()} to {idx.index.max().date()}")
    print("Fetching NIFTY 50 constituent data...")
    stocks = fetch_nifty_50_data()
    print(f"Stocks: {len(stocks)} symbols fetched")
    for s, df in stocks.items():
        print(f"  {s}: {len(df)} rows")
    print("Done.")
