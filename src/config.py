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
REGIME_REDUCED = 1.0

# Entry conditions
ENTRY_DRAWDOWN = -0.05
ENTRY_VOLUME_RATIO = 1.0
ENTRY_PRICE_VS_LOW = 1.05
ENTRY_PRICE_VS_HIGH_MAX = 0.98
HORIZON = 20

# Regime thresholds (20d_return_min, 20d_return_max, multiplier)
REGIME_MULTIPLIERS = [
    (8,    float("inf"), 1.0),    # Strong Bull: 1 position
    (3,    8,             1.0),    # Bull: 1 position
    (-3,   3,             1.0),    # Sideways: 1 position
    (float("-inf"), -3,   1.0),    # Bear/Crash: 1 position
]

# Sector concentration
MAX_SECTOR_POSITIONS = 2
