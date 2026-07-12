from __future__ import annotations

"""Centralized configuration for the trading system."""

# Capital
CAPITAL = 10_000_000

# Execution costs
SLIPPAGE = 0.001
BROKERAGE = 0.0005

# Position limits
MAX_POSITIONS = 1
MIN_POSITIONS = 1

# Exit parameters
HARD_STOP = -0.08
PROFIT_TARGET_1 = 0.12
PROFIT_TARGET_2 = 0.18
TRAIL_ACTIVATE = 0.10
TRAIL_DISTANCE = 0.12
TIME_STOP_DAYS = 20

# Risk limits
MAX_DAILY_LOSS = 0.02
MAX_DRAWDOWN_DISABLE = 0.15

# Regime position sizing (all 1.0 for single-position strategy)
REGIME_NORMAL = 1.0

# Regime rules: (20d_return_min, 20d_return_max, label, max_positions, action, note)
# Single source of truth for regime classification across daily_scan.py and reporting.py
REGIME_RULES = [
    (8,    float("inf"), "Strong Bull", 1, "Reduce",    "Rare regime. Trades infrequent."),
    (3,    8,             "Bull",        1, "Skip or 1", "25% win rate. Avoid."),
    (-3,   3,             "Sideways",    1, "Full deploy", "Core regime. 59% of market."),
    (-8,   -3,            "Bear",        1, "Full deploy", "Best regime. 78% win rate."),
    (float("-inf"), -8,   "Crash",       1, "Full deploy", "Best regime. 71% win rate."),
]

# Entry conditions
ENTRY_DRAWDOWN = -0.05
ENTRY_VOLUME_RATIO = 1.0
ENTRY_PRICE_VS_LOW = 1.05
ENTRY_PRICE_VS_HIGH_MAX = 0.98
HORIZON = 20

# Sector concentration
MAX_SECTOR_POSITIONS = 2

# Momentum strategy params
MOM_MAX_POSITIONS = 10
MOM_MIN_POSITIONS = 3
MOM_STOP_LOSS = -0.15
MOM_TRAIL_ACTIVATE = 0.20
MOM_TRAIL_DISTANCE = 0.15
MOM_MIN_VOLUME = 500_000
MOM_LOOKBACK = 252
MOM_MAX_PRICE = 100_000
MOM_MIN_PRICE = 20
MOM_SECTOR_MAX = 3
