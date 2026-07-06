def print_report(pf):
    perf = pf.get_performance()
    print("\n" + "="*70)
    print("VOLATILITY CONTRARIAN - PERFORMANCE REPORT")
    print("="*70)
    print(f"  Total Return            {perf['total_return_pct']:.2f}%")
    print(f"  CAGR                    {perf['cagr_pct']:.2f}%")
    print(f"  Volatility              {perf['volatility_pct']:.2f}%")
    print(f"  Sharpe Ratio            {perf['sharpe']:.2f}")
    print(f"  Sortino Ratio           {perf['sortino']:.2f}")
    print(f"  Max Drawdown            {perf['max_drawdown_pct']:.2f}%")
    print(f"  Total Trades            {perf['total_trades']}")
    print(f"  Win Rate                {perf['win_rate_pct']:.1f}%")
    print(f"  Profit Factor           {perf['profit_factor']:.2f}")
    print(f"  Final Equity            INR {perf['final_equity']:,.2f}")
    print(f"  Peak Equity             INR {perf['peak_equity']:,.2f}")
    print(f"  Current Positions       {perf['num_positions']}")
    if perf.get("disabled"):
        print("  ⚠️ PORTFOLIO DISABLED (max drawdown)")
    print("="*70 + "\n")

    trades_df = pf.get_trades_summary()
    if not trades_df.empty:
        print("\nEXIT REASON BREAKDOWN")
        for reason, g in trades_df.groupby("exit_reason"):
            print(f"  {reason:<25} {len(g):4d} trades | Avg PnL: {g['pnl_pct'].mean():+.2f}%")
