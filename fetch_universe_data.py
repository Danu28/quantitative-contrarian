"""Fetch daily OHLCV data for any universe and cache in SQLite.

Usage:
    python fetch_universe_data.py --universe nifty50
    python fetch_universe_data.py --universe niftymidcap150 --years 5
    python fetch_universe_data.py --universe universe/nifty500.json --db data/market_data.db
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from reverse_engineer.universe_loader import _resolve_json_path, UNIVERSE_DIR

DB_PATH = Path(__file__).resolve().parent / "data" / "market_data.db"


def get_db(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            symbol TEXT PRIMARY KEY,
            company_name TEXT,
            sector TEXT,
            universe_slug TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_ohlcv (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            adj_close REAL,
            PRIMARY KEY (symbol, date)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_daily_symbol ON daily_ohlcv(symbol)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_ohlcv(date)
    """)
    conn.commit()
    return conn


def get_cached_dates(conn: sqlite3.Connection, symbol: str) -> set[str]:
    rows = conn.execute(
        "SELECT date FROM daily_ohlcv WHERE symbol = ?", (symbol,)
    ).fetchall()
    return {r[0] for r in rows}



def store_stock(conn: sqlite3.Connection, symbol: str, company_name: str, sector: str, universe_slug: str):
    conn.execute(
        """INSERT OR REPLACE INTO stocks (symbol, company_name, sector, universe_slug)
           VALUES (?, ?, ?, ?)""",
        (symbol, company_name, sector, universe_slug),
    )
    conn.commit()


def store_batch(conn: sqlite3.Connection, symbol: str, df: pd.DataFrame):
    if df.empty:
        return
    records = []
    for idx, row in df.iterrows():
        date_str = pd.Timestamp(idx).strftime("%Y-%m-%d")
        records.append((
            symbol, date_str,
            float(row.get("open", 0)),
            float(row.get("high", 0)),
            float(row.get("low", 0)),
            float(row.get("close", 0)),
            int(row.get("volume", 0)),
            float(row.get("adj_close", row.get("close", 0))),
        ))
    conn.executemany(
        """INSERT OR REPLACE INTO daily_ohlcv
           (symbol, date, open, high, low, close, volume, adj_close)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        records,
    )
    conn.commit()


def fetch_symbol_data(
    conn: sqlite3.Connection,
    symbol: str,
    years: int = 10,
    force: bool = False,
) -> pd.DataFrame:
    cached_dates = get_cached_dates(conn, symbol)
    if cached_dates:
        latest = max(cached_dates)
        today = datetime.now().strftime("%Y-%m-%d")
        if latest >= today:
            print(f"  {symbol}: up to date ({latest})")
            df = pd.read_sql_query(
                "SELECT date, open, high, low, close, volume, adj_close "
                "FROM daily_ohlcv WHERE symbol = ? ORDER BY date",
                conn, params=(symbol,), index_col="date", parse_dates=["date"],
            )
            return df

    print(f"  {symbol}: fetching...")
    start = datetime.now() - timedelta(days=365 * years)
    df = yf.download(symbol, start=start, progress=False, auto_adjust=True)
    if df.empty:
        print(f"  {symbol}: WARNING - no data returned")
        return df

    df.index = pd.to_datetime(df.index)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]

    store_batch(conn, symbol, df)
    print(f"  {symbol}: stored {len(df)} rows")
    return df


def load_universe(universe_slug_or_path: str) -> dict:
    json_path = _resolve_json_path(universe_slug_or_path)
    with open(json_path, encoding="utf-8") as f:
        config = json.load(f)
    config["symbols"] = [c["symbol"] for c in config["constituents"]]
    return config


def validate_symbols(symbols: list[str]) -> list[str]:
    """Quick pre-flight check via yfinance info. Returns list of invalid symbols."""
    bad: list[str] = []
    for sym in symbols:
        print(f"  {sym}...", end=" ")
        try:
            info = yf.Ticker(sym).info
            if not info or "regularMarketPrice" not in info:
                info = yf.download(sym, period="5d", progress=False, auto_adjust=True)
                if info.empty:
                    print("NOT FOUND")
                    bad.append(sym)
                else:
                    print("OK")
            else:
                print("OK")
        except Exception:
            try:
                df = yf.download(sym, period="5d", progress=False, auto_adjust=True)
                if df.empty:
                    print("NOT FOUND")
                    bad.append(sym)
                else:
                    print("OK")
            except Exception:
                print("NOT FOUND")
                bad.append(sym)
    return bad


def fetch_universe(
    universe_slug_or_path: str,
    years: int = 10,
    db_path: str | Path = DB_PATH,
    force: bool = False,
    delay: float = 0.5,
    continue_on_error: bool = False,
    validate_only: bool = False,
):
    config = load_universe(universe_slug_or_path)
    slug = config.get("slug", Path(universe_slug_or_path).stem)
    universe_name = config.get("name", slug)
    constituents = config["constituents"]
    symbols = config["symbols"]

    print(f"Universe: {universe_name} ({len(symbols)} stocks)")
    print(f"DB: {db_path}")
    print()

    print("Pre-flight symbol validation...")
    bad = validate_symbols(symbols)
    if bad:
        print(f"\nERROR: {len(bad)} invalid symbol(s) found:")
        for s in bad:
            print(f"  {s}")
        print("\nFix the universe JSON or use --continue-on-error to skip bad symbols.")
        sys.exit(1)

    if validate_only:
        print("\nAll symbols valid. No data fetched (--validate-only).")
        return {}

    print()

    conn = get_db(Path(db_path))

    for c in constituents:
        store_stock(
            conn,
            c["symbol"],
            c.get("companyName", c["symbol"]),
            c.get("sector", "Unknown"),
            slug,
        )

    all_dfs: dict[str, pd.DataFrame] = {}
    errors = 0
    for i, c in enumerate(constituents, 1):
        sym = c["symbol"]
        print(f"[{i}/{len(constituents)}]", end=" ")
        df = fetch_symbol_data(conn, sym, years=years, force=force)
        if not df.empty:
            all_dfs[sym] = df
        else:
            errors += 1
            if not continue_on_error:
                conn.close()
                print(f"\nFATAL: {sym} returned no data. Aborting. Use --continue-on-error to skip bad symbols.")
                sys.exit(1)
        if i < len(constituents):
            time.sleep(delay)

    conn.close()
    result = f"Done. Fetched {len(all_dfs)}/{len(symbols)} symbols."
    if errors:
        result += f" ({errors} errors)"
    print(f"\n{result}")
    return all_dfs


def query(
    universe_slug_or_path: str,
    db_path: str | Path = DB_PATH,
    since: str | None = None,
) -> pd.DataFrame:
    config = load_universe(universe_slug_or_path)
    symbols = config["symbols"]
    conn = get_db(Path(db_path))

    if since:
        rows = conn.execute(
            f"SELECT * FROM daily_ohlcv WHERE symbol IN ({','.join('?' * len(symbols))}) AND date >= ? ORDER BY symbol, date",
            (*symbols, since),
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT * FROM daily_ohlcv WHERE symbol IN ({','.join('?' * len(symbols))}) ORDER BY symbol, date",
            symbols,
        ).fetchall()

    df = pd.DataFrame(rows, columns=["symbol", "date", "open", "high", "low", "close", "volume", "adj_close"])
    df["date"] = pd.to_datetime(df["date"])
    conn.close()
    return df


def available_universes() -> list[dict]:
    from reverse_engineer.universe_loader import list_available_detailed
    return list_available_detailed()


def main():
    parser = argparse.ArgumentParser(description="Fetch market data for any stock universe")
    parser.add_argument("--universe", "-u", default="nifty50",
                        help="Universe slug (nifty50, nifty500, niftymidcap150) or path to JSON")
    parser.add_argument("--db", default=str(DB_PATH),
                        help=f"SQLite DB path (default: {DB_PATH})")
    parser.add_argument("--years", type=int, default=10,
                        help="Years of history to fetch (default: 10)")
    parser.add_argument("--force", action="store_true",
                        help="Force re-fetch even if cached")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Delay between API requests in seconds (default: 0.5)")
    parser.add_argument("--query", "-q", nargs="?", const="1900-01-01",
                        help="Query cached data (optionally since YYYY-MM-DD)")
    parser.add_argument("--list", "-l", action="store_true",
                        help="List available universes")
    parser.add_argument("--validate-only", action="store_true",
                        help="Only validate symbols, don't fetch data")
    parser.add_argument("--continue-on-error", action="store_true",
                        help="Skip bad symbols instead of aborting")

    args = parser.parse_args()

    if args.list:
        for u in available_universes():
            flag = " ERROR" if u.get("error") else ""
            print(f"  {u['slug']:20s}  {u['name']:30s}  {u['n_constituents']:4d} stocks{flag}")
        return

    if args.query:
        since = None if args.query == "1900-01-01" else args.query
        df = query(args.universe, args.db, since=since)
        if df.empty:
            print("No cached data found. Run without --query to fetch first.")
        else:
            print(f"{len(df)} rows")
            print(df.to_string(index=False))
        return

    fetch_universe(args.universe, years=args.years, db_path=args.db,
                   force=args.force, delay=args.delay,
                   continue_on_error=args.continue_on_error,
                   validate_only=args.validate_only)


if __name__ == "__main__":
    main()
