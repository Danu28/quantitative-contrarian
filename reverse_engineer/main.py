import pandas as pd
from pathlib import Path
from data import fetch_nifty_50_data
from characteristics import precompute_all_characteristics
from signal_generator import generate_signals, HORIZON
from portfolio import Portfolio

HERE = Path(__file__).parent
STATE_DIR = HERE / "state"
STATE_DIR.mkdir(exist_ok=True)
STATE_FILE = STATE_DIR / "portfolio.parquet"
TRADES_FILE = STATE_DIR / "trades.parquet"
DATA_DIR = HERE.parent / "data"


def load_portfolio() -> Portfolio:
    pf = Portfolio()
    if STATE_FILE.exists():
        df = pd.read_parquet(STATE_FILE)
        if not df.empty:
            last = df.iloc[-1]
            pf.cash = float(last["cash"])
            pf.peak_equity = float(last.get("peak_equity", pf.starting_capital))
            pf.disabled = bool(last.get("disabled", False))
    if TRADES_FILE.exists():
        trades_df = pd.read_parquet(TRADES_FILE)
        if not trades_df.empty:
            pf.trades = trades_df.to_dict("records")
    return pf


def save_portfolio(pf: Portfolio):
    eq_df = pd.DataFrame(pf.equity_curve)
    if not eq_df.empty:
        eq_df["peak_equity"] = pf.peak_equity
        eq_df["disabled"] = pf.disabled
        eq_df.to_parquet(STATE_FILE)
    trades_df = pf.get_trades_summary()
    if not trades_df.empty:
        trades_df.to_parquet(TRADES_FILE)


RESEARCH_YEARS = 3


def run_daily(verbose: bool = True):
    pf = load_portfolio()
    if pf.disabled:
        if verbose:
            print("Portfolio disabled due to max drawdown. Skipping.")
        return pf

    data = fetch_nifty_50_data(years=RESEARCH_YEARS)
    char_data = precompute_all_characteristics(data, window=HORIZON)

    all_dates = sorted(set(
        d for s in char_data for d in char_data[s].index
    ))
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=365 * RESEARCH_YEARS)
    all_dates = [d for d in all_dates if d >= cutoff]

    last_processed = None
    if pf.equity_curve:
        last_processed = pf.equity_curve[-1]["date"]

    new_dates = [d for d in all_dates if last_processed is None or d > last_processed]
    if not new_dates:
        if verbose:
            print("No new data to process.")
        return pf

    if verbose:
        print(f"Processing {len(new_dates)} new trading days...")

    for i, date in enumerate(new_dates):
        prices = {
            s: data[s].loc[date, "close"]
            for s in data if date in data[s].index
        }
        sig = generate_signals(data, char_data, date)
        pf.process_day(sig, prices, date)

    save_portfolio(pf)

    perf = pf.get_performance()
    if verbose:
        print("\n" + "="*60)
        print("VOLATILITY CONTRARIAN — Daily Run")
        print("="*60)
        print(f"  Date range:    {new_dates[0].date()} → {new_dates[-1].date()}")
        print(f"  Open positions: {len(pf.positions)}")
        print(f"  Total trades:   {perf['total_trades']}")
        print(f"  Portfolio Eq:   INR {perf['final_equity']:,.2f}")
        print(f"  CAGR:           {perf['cagr_pct']:.2f}%")
        top = pf.get_positions_summary()
        if not top.empty:
            print("\nOpen Positions:")
            for _, row in top.iterrows():
                print(f"  {row['symbol']:<15} Entry={row['entry_price']:.2f}  Shares={row['shares']}  Since={row['entry_date'].date()}")
        if pf.disabled:
            print("\n⚠️ EMERGENCY: Max drawdown limit hit. Portfolio disabled.")
    return pf


if __name__ == "__main__":
    run_daily(verbose=True)
