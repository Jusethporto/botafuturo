"""Default (non-secret) configuration values for the trading bot.

These are the single source of truth for default risk/stake/strategy
parameters. `config/settings.py` uses these as the pydantic default values
for the corresponding `Settings` fields, so they always stay overridable via
environment variables or a `.env` file without needing to touch this module.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Final

STARTING_BALANCE: Final[Decimal] = Decimal("1000.00")
PAYOUT_RATE: Final[Decimal] = Decimal("0.85")
STAKE_MODE: Final[str] = "fixed"
STAKE_AMOUNT: Final[Decimal] = Decimal("10.00")
MAX_DAILY_LOSS_PCT: Final[Decimal] = Decimal("0.05")
MAX_CONSECUTIVE_LOSSES: Final[int] = 5
DEFAULT_EXPIRY_S: Final[int] = 60
SMA_FAST_PERIOD: Final[int] = 5
SMA_SLOW_PERIOD: Final[int] = 20
