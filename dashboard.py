import sys
import streamlit as st
import pandas as pd
from pathlib import Path

RE_DIR = Path(__file__).parent / "reverse_engineer"
sys.path.insert(0, str(RE_DIR))
from main import run_daily  # noqa: E402
from portfolio import Portfolio  # noqa: E402

STATE_DIR = RE_DIR / "state"
TRADES_FILE = STATE_DIR / "trades.parquet"
STATE_FILE = STATE_DIR / "portfolio.parquet"

st.set_page_config(
    page_title="Volatility Contrarian",
    page_icon="📊",
    layout="wide",
)

st.title("Volatility Contrarian")
st.markdown("NIFTY 50 | Horizon: 20 days | Rebalance: Weekly (Fri)")


@st.cache_data(ttl=3600)
def load_portfolio_state():
    pf = Portfolio()
    if STATE_FILE.exists():
        df = pd.read_parquet(STATE_FILE)
        if not df.empty:
            last = df.iloc[-1]
            pf.cash = float(last["cash"])
            pf.peak_equity = float(last.get("peak_equity", pf.starting_capital))
            pf.disabled = bool(last.get("disabled", False))
            for _, row in df.iterrows():
                pf.equity_curve.append({
                    "date": row.name if isinstance(row.name, pd.Timestamp) else pd.Timestamp(row.name),
                    "equity": float(row["equity"]),
                    "cash": float(row["cash"]),
                    "positions_value": float(row["positions_value"]),
                    "num_positions": int(row["num_positions"]),
                })
    if TRADES_FILE.exists():
        trades_df = pd.read_parquet(TRADES_FILE)
        if not trades_df.empty:
            pf.trades = trades_df.to_dict("records")
    return pf


@st.cache_data(ttl=3600)
def load_current_signals():
    try:
        from reverse_engineer.signal_generator import generate_todays_signals
        return generate_todays_signals()
    except Exception:
        return pd.DataFrame()


pf = load_portfolio_state()
signals = load_current_signals()
perf = pf.get_performance()

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    metric_val = f"{perf.get('cagr_pct', 0):.1f}%"
    st.metric("CAGR", metric_val)
with col2:
    st.metric("Max DD", f"{perf.get('max_drawdown_pct', 0):.1f}%")
with col3:
    st.metric("Win Rate", f"{perf.get('win_rate_pct', 0):.0f}%")
with col4:
    st.metric("Trades", str(perf.get("total_trades", 0)))
with col5:
    status = "⚠️ Disabled" if pf.disabled else "✅ Active"
    st.metric("Status", status)

st.subheader("Open Positions")
positions_df = pf.get_positions_summary()
if not positions_df.empty:
    display = positions_df.copy()
    st.dataframe(display, width="stretch", hide_index=True)
else:
    st.info("No open positions.")

st.subheader("Current Signals")
if not signals.empty:
    display = signals[["rank", "symbol", "close", "conviction"]].copy()
    st.dataframe(display, width="stretch", hide_index=True)
else:
    st.info("No signals generated today.")

st.subheader("Equity Curve")
eq = pd.DataFrame(pf.equity_curve).set_index("date") if pf.equity_curve else pd.DataFrame()
if not eq.empty:
    eq["equity"] = eq["equity"].astype(float)
    st.line_chart(eq["equity"])
    cummax = eq["equity"].cummax()
    dd = ((eq["equity"] - cummax) / cummax * 100).rename("drawdown_pct")
    st.line_chart(dd)
else:
    st.info("No equity history available.")

st.subheader("Recent Trades")
trades_df = pf.get_trades_summary()
if not trades_df.empty:
    st.dataframe(trades_df.tail(10), width="stretch", hide_index=True)
else:
    st.info("No trades yet.")

with st.expander("Run Daily Update"):
    if st.button("Refresh Data & Signals"):
        with st.spinner("Running daily update..."):
            run_daily(verbose=False)
            st.cache_data.clear()
            st.rerun()

st.caption(
    f"Last updated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} | "
    f"Data source: Yahoo Finance (yfinance)"
)

if __name__ == "__main__":
    print("Run with: streamlit run dashboard.py --server.port 8501")
