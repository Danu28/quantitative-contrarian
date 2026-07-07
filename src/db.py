from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

UNIVERSE_DIR = Path(__file__).resolve().parent.parent / "universe"
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "market_data.db"
KNOWN_SLUGS: dict[str, str] = {
    "nifty50": "nifty50.json",
    "nifty500": "nifty500.json",
}


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


def _resolve_json_path(name_or_path: str) -> Path:
    p = Path(name_or_path)
    if p.exists() and p.suffix == ".json":
        return p.resolve()
    slug = name_or_path.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    fname = KNOWN_SLUGS.get(slug)
    if fname is not None:
        return (UNIVERSE_DIR / fname).resolve()
    alt = UNIVERSE_DIR / f"{slug}.json"
    if alt.exists():
        return alt.resolve()
    raise FileNotFoundError(
        f"Universe '{name_or_path}' not found. "
        f"Known slugs: {list(KNOWN_SLUGS.keys())}. "
        f"Or provide path to a JSON file."
    )


def load_universe(universe_slug_or_path: str) -> dict:
    json_path = _resolve_json_path(universe_slug_or_path)
    with open(json_path, encoding="utf-8") as f:
        config = json.load(f)
    config["symbols"] = [c["symbol"] for c in config["constituents"]]
    return config


def get_symbols(universe_slug_or_path: str) -> list[str]:
    return load_universe(universe_slug_or_path)["symbols"]


def get_sector_map(universe_slug_or_path: str) -> dict[str, str]:
    config = load_universe(universe_slug_or_path)
    return {c["symbol"]: c.get("sector", "Unknown") for c in config["constituents"]}


def list_available_detailed() -> list[dict]:
    results = []
    for p in sorted(UNIVERSE_DIR.glob("*.json")):
        try:
            with open(p) as f:
                c = json.load(f)
            results.append({
                "slug": c.get("slug", p.stem),
                "name": c.get("name", p.stem),
                "n_constituents": len(c.get("constituents", [])),
                "file": str(p),
            })
        except Exception:
            results.append({"slug": p.stem, "name": p.stem, "n_constituents": 0, "file": str(p), "error": True})
    return results


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
    cached_dates: set[str] = set()
    if not force:
        cached_dates = get_cached_dates(conn, symbol)
        if cached_dates:
            latest = max(cached_dates)
            today = datetime.now().strftime("%Y-%m-%d")
            if latest >= today:
                print(f"  {symbol}: up to date ({latest})")
                return pd.read_sql_query(
                    "SELECT date, open, high, low, close, volume, adj_close "
                    "FROM daily_ohlcv WHERE symbol = ? ORDER BY date",
                    conn, params=(symbol,), index_col="date", parse_dates=["date"],
                )

    print(f"  {symbol}: fetching...")
    if cached_dates:
        start = datetime.strptime(latest, "%Y-%m-%d") - timedelta(days=5)
    else:
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


def validate_symbols(symbols: list[str]) -> list[str]:
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
                print(f"\nFATAL: {sym} returned no data. Aborting.")
                sys.exit(1)
        if i < len(constituents):
            time.sleep(delay)

    conn.close()
    result = f"Done. Fetched {len(all_dfs)}/{len(symbols)} symbols."
    if errors:
        result += f" ({errors} errors)"
    print(f"\n{result}")
    return all_dfs


def fetch_missing_data(
    universe_slug_or_path: str,
    db_path: str | Path = DB_PATH,
    years: int = 10,
):
    config = load_universe(universe_slug_or_path)
    symbols = config["symbols"]
    conn = get_db(Path(db_path))

    latest = conn.execute(
        f"SELECT MAX(date) FROM daily_ohlcv WHERE symbol IN ({','.join('?' * len(symbols))})",
        symbols,
    ).fetchone()[0]
    today = datetime.now().strftime("%Y-%m-%d")

    if latest and latest >= today:
        conn.close()
        return

    print(f"  Latest data: {latest}. Fetching updates from yfinance...")
    for i, sym in enumerate(symbols, 1):
        print(f"  [{i}/{len(symbols)}]", end=" ")
        fetch_symbol_data(conn, sym, years=years)
    conn.close()


def load_data(
    universe_slug_or_path: str,
    db_path: str | Path = DB_PATH,
    since: str | None = None,
    auto_fetch: bool = True,
) -> pd.DataFrame:
    config = load_universe(universe_slug_or_path)
    symbols = config["symbols"]

    if auto_fetch:
        fetch_missing_data(universe_slug_or_path, db_path)

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
