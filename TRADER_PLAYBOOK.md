# Contrarian Strategy — Trader's Playbook

**Version:** 1.0 | **Universe:** NIFTY 50 | **Rebalance:** Weekly (Friday) | **Hold:** 20 trading days

---

## 1. Before You Start

### Account Requirements
- **Broker**: Any Indian broker with NSE cash segment access (Zerodha, Angel One, ICICI Direct, etc.)
- **Capital**: ₹10L minimum (3 positions × ~₹3L each). Strategy scales linearly — halve capital = halve position sizes.
- **Demat**: Required for equity delivery holding
- **Margins**: Delivery trading only (no margin needed for cash-and-carry)

### Strategy Summary
- Buy NIFTY 50 stocks that have dropped 8%+ in 20 days with above-average volume & volatility
- Hold for up to 20 trading days
- Sell at +12% (half), +18% (rest), -8% (stop), or trail (activate at +10%, stop at -12% from high)
- Rebalance every Friday — only enter new positions on Friday
- **Max 3 positions** at any time

---

## 2. Friday Rebalance — Step by Step

### 9:00 AM — Pre-Market Check
```python
# Run the daily scan (already configured)
python daily_scan.py --output report.html
```

Open `daily_scan_report.html`. Check:

**Step A — Market Regime**
```
NIFTY 20d return:        What to do:
+3% to +8% (Bull)        → Skip or max 1 position (25% win rate in bull)
-3% to +3% (Sideways)    → Full deploy, 3 positions (core regime)
-8% to -3% (Bear)        → Full deploy, 3 positions (77.8% win rate)
< -8% (Crash)            → Full deploy, 3 positions (best avg return +7.2%)
```

**Step B — Check Signals**
- 0 signals: Skip week. Normal. Try again next Friday.
- 1-2 signals: Enter all (up to regime max)
- 3+ signals: Enter top 3 by conviction score

**Step C — Check Recent Performance**
- 2+ hard stops this week? → Reduce entries by 1
- NIFTY ATR up >50% in a week? → Reduce entries by 1

### 3:20 PM — Place Entry Orders

For each signal you plan to enter:

**Order Type:** Market order (NIFTY 50 stocks are liquid enough — market order fills at or near close)

**Position Size:**
```
capital_per_position = available_cash / (current_positions + new_entries + 3)
```
Where `+3` is the reserve factor (keeps 3 position-equivalents in cash).

**Example** (₹10L capital, 2 current positions, 2 new entries):
```
cash_per = 10,00,000 / (2 + 2 + 3) = ₹1,42,857 per position
shares = floor(1,42,857 / entry_price)
```

### 3:30 PM — Market Close
- Check that all orders filled
- If partial fill (only 1 of 2 filled), accept it. Don't chase.
- Log entries in trade journal (see Section 6)

---

## 3. Exit Monitoring (Monday–Thursday)

### Passive Monitoring (No Daily Action Required)
The strategy has 5 automatic exits. You don't need to watch the screen:

| Exit Type | Trigger | Action | How to Execute |
|-----------|---------|--------|----------------|
| **Profit Target 1** | Price hits +12% | Sell HALF the position | Set GTT (Good Till Triggered) sell order at Target1 price |
| **Profit Target 2** | Price hits +18% | Sell REMAINING position | Set GTT at Target2 price after Target1 hits |
| **Hard Stop** | Price hits -8% | Sell ENTIRE position | Set GTT stop-loss at HardStop price |
| **Trailing Stop** | Price up 10%+, then drops 12% from high | Sell ENTIRE position | Cannot automate with GTT. Requires manual check or bracket order. |
| **Time Stop** | 20 trading days elapsed | Sell at market on day 20 | Manual — check calendar on day 20 |

### Recommended: Use GTT Orders
Most Indian brokers support GTT (Good Till Triggered) orders:
- **Set on Friday** after entry:
  1. GTT Sell @ Target1 price (for half quantity)
  2. GTT Stop-loss @ HardStop price (for half quantity)
  3. GTT Sell @ Target2 price (for remaining half) — activate only after Target1 hits

- **Check weekly** (next Friday): update GTTs if price moved significantly

### Trailing Stop (Manual Only)
The trailing stop activates at +10% and trails by -12% from the highest price since entry.
- Check once per week (Friday during scan): if stock is up 10%+, note the highest close
- If current price < high × 0.88, sell at market
- This is the hardest rule to follow manually. Consider accepting the trade-off: if you miss the trail, the time stop will exit at day 20 anyway.

### Time Stop Reminder
- After entry, note `entry_date + 20 trading days` on your calendar
- On that day, sell at market regardless of price
- Most useful when a position is flat or slightly negative after 20 days

---

## 4. Position Sizing (for Any Account Size)

### Formula
```
base_capital = min(account_value, 10_000_000)  # Strategy validated up to ₹1Cr
scaling_factor = account_value / base_capital

max_positions = 3 × regime_multiplier
               (1.0 for Sideways/Bear/Crash, 0.33 for Bull, 0.67 for Strong Bull)

cash_per_position = account_value / (current_positions + new_entries + 3)
shares = floor(cash_per_position / entry_price)
```

### Examples

| Account Size | Regime | Max Positions | Per Position | Shares (₹1,000 stock) |
|-------------|--------|:-------------:|:------------:|:---------------------:|
| ₹5L | Sideways | 3 | ~₹62,500 | 62 |
| ₹10L | Sideways | 3 | ~₹1,42,857 | 142 |
| ₹25L | Sideways | 3 | ~₹3,57,143 | 357 |
| ₹1Cr | Sideways | 3 | ~₹14,28,571 | 1,428 |
| ₹10L | Bull (skip) | 1 | ~₹2,00,000 | 200 |
| ₹10L | Bear (full) | 3 | ~₹1,42,857 | 142 |

### Capital Utilization Expectation
- Average 5 positions held across weeks (carryover + new entries)
- Typical cash deployed: 50-70% of account
- Reserve cash: 30-50% (earns nothing, but available for dips)

---

## 5. Risk Management

### Built-in Protection
| Risk | Protection |
|------|-----------|
| Single stock crash | Hard stop at -8% (exit at ~-8.15% after costs) |
| Market-wide crash | More signals fire (anti-fragile: most trades in Crash regime avg +7.2%) |
| Illiquid stock | Volume condition filters out low-volume days |
| Sector concentration | Max 3 positions, natural diversification from NIFTY 50 spread |
| Account drawdown >15% | Emergency stop — exit all positions, stop trading |

### Red Flags (When to Pause)
- **3 consecutive Fridays with 0 signals**: Market likely in strong bull. Don't force trades.
- **4+ hard stops in a month**: Regime may have changed. Check NIFTY 20d trend.
- **Strategy down >10% from peak**: Something may be broken. Review all assumptions.
- **NIFTY 50 constituent change**: If a stock you hold is removed from NIFTY 50, exit at next Friday.

### What NOT to Do
- ❌ Don't add to losing positions (no averaging down)
- ❌ Don't skip a rebalance because last trade lost money (sequence risk)
- ❌ Don't exit early because a position is +5% after 5 days (target is +12%)
- ❌ Don't enter mid-week (wait for Friday — daily entries tested and underperform)
- ❌ Don't override the conviction ranking (it's optimized for risk-adjusted returns)

---

## 6. Record Keeping

### Trade Journal (One Row Per Trade)
```
Date        Symbol       Entry    Shares  Exit    PnL%   Exit Reason   Days Held
2026-07-07  RELIANCE.NS  2,850    142     3,192   +12%   Target1_Half  14
2026-07-07  RELIANCE.NS  2,850    142     3,363   +18%   Target2       20
2026-07-07  TCS.NS       3,900    51      3,588   -8%    Hard_Stop     8
```

### Monthly Performance Check
At end of each month, compare to benchmarks:
- **Expected**: ~0.6% monthly return (7.3% CAGR ÷ 12)
- **MaxDD**: -5% maximum drawdown from peak
- **Win Rate**: ~55% target
- **If below these for 3 consecutive months**: Investigate. May need strategy review.

### Tax Notes (India)
- **Holding < 12 months**: STCG at 15% on gains
- **Holding > 12 months**: LTCG at 10% on gains over ₹1L
- Since most trades hold 20 days, nearly all are STCG
- Offset losses against gains in same financial year
- Keep records of all trades for ITR filing

---

## 7. Performance Expectations

| Metric | Expected | Source |
|--------|:--------:|--------|
| CAGR | 5-8% | Backtested 5.21-7.31% over 3 years |
| Max Drawdown | -5% | Historical max, typically -3% to -5% |
| Sharpe | 0.10-0.15 | Low because cash drags returns |
| Win Rate | 50-55% | 53.1% in latest test |
| Avg Win | +6-7% | Time stops + profit targets |
| Avg Loss | -9-10% | Hard stops dominate losses |
| Trades per Year | ~20-25 | 64 trades over 3 years |
| Avg Hold | 17-20 days | 74% exit by time stop at 20d |
| Capital Employed | 50-70% | Cash reserve maintained |

### What This Strategy IS
- A **capital preservation** strategy that generates moderate returns
- A **portfolio diversifier** (negatively correlated with bull markets)
- An **anti-fragile** component that performs best in downturns

### What This Strategy IS NOT
- Not a get-rich-quick system
- Not a market-neutral strategy
- Not suitable for leveraged trading
- Not backtested outside Indian equities

---

## 8. Emergency Procedures

| Situation | Action |
|-----------|--------|
| Broker platform down on Friday | Try mobile app. If both down, skip rebalance. |
| Stock gaps below hard stop at open | Accept the loss. Exit at whatever price available. |
| NIFTY 50 constituent removed | Exit position at next Friday rebalance. |
| Personal emergency (can't trade) | It's OK to skip a week. Strategy survives 15-day gaps. |
| Strategy stops working (6+ months negative) | Full review. Market regime may have structurally changed. |

---

## 9. Tools Reference

### daily_scan.py
```
python daily_scan.py --output report.html
```
Shows: signals, entry prices, exit targets, market regime, conviction scores

### Expected Monthly Cadence
```
Week 1: Enter 2-3 positions on Friday
Week 2: Monitor exits (GTTs handle most). Possibly 1 new entry.
Week 3: Positions from Week 1 start hitting time stops. New entries.
Week 4: Positions from Week 2 hit time stops. Fresh cycle.
```

A typical month: 4-6 new entries, 4-6 exits, 4-6 positions held at any time.

---

## 10. Quick Reference Card (Print This)

```
┌──────────────────────────────────────────────────────────────┐
│  FRIDAY CHECKLIST                                           │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  □ Run `python daily_scan.py --output report.html`           │
│  □ Check NIFTY 20d trend → determine regime action           │
│  □ Check signal count → how many to enter                    │
│  □ Check recent hard stops → reduce if >2 this week         │
│  □ Place market orders at 3:20 PM                            │
│  □ Set GTT stop-loss at HardStop price (half quantity)       │
│  □ Set GTT take-profit at Target1 price (half quantity)      │
│  □ Log entries in trade journal                              │
│  □ Check exiting positions for time stop (20d)               │
│                                                              │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  REGIME QUICK REFERENCE                                     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  If NIFTY 20d > +3%    → Skip or 1 position (bull)          │
│  If NIFTY 20d +3%/-3% → Full deploy (sideways)              │
│  If NIFTY 20d < -3%    → Full deploy (bear/crash — best!)   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
