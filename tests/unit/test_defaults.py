"""Tests for config/defaults.py — the non-secret default configuration
values used as pydantic defaults in config/settings.py.
"""
from __future__ import annotations

from decimal import Decimal

from botafuturo.config import defaults


def test_starting_balance() -> None:
    assert defaults.STARTING_BALANCE == Decimal("1000.00")
    assert isinstance(defaults.STARTING_BALANCE, Decimal)


def test_payout_rate() -> None:
    assert defaults.PAYOUT_RATE == Decimal("0.85")
    assert isinstance(defaults.PAYOUT_RATE, Decimal)


def test_stake_mode() -> None:
    assert defaults.STAKE_MODE == "fixed"
    assert isinstance(defaults.STAKE_MODE, str)


def test_stake_amount() -> None:
    assert defaults.STAKE_AMOUNT == Decimal("10.00")
    assert isinstance(defaults.STAKE_AMOUNT, Decimal)


def test_max_daily_loss_pct() -> None:
    assert defaults.MAX_DAILY_LOSS_PCT == Decimal("0.05")
    assert isinstance(defaults.MAX_DAILY_LOSS_PCT, Decimal)


def test_max_consecutive_losses() -> None:
    assert defaults.MAX_CONSECUTIVE_LOSSES == 5
    assert isinstance(defaults.MAX_CONSECUTIVE_LOSSES, int)


def test_default_expiry_s() -> None:
    assert defaults.DEFAULT_EXPIRY_S == 60
    assert isinstance(defaults.DEFAULT_EXPIRY_S, int)


def test_sma_fast_period() -> None:
    assert defaults.SMA_FAST_PERIOD == 5
    assert isinstance(defaults.SMA_FAST_PERIOD, int)


def test_sma_slow_period() -> None:
    assert defaults.SMA_SLOW_PERIOD == 20
    assert isinstance(defaults.SMA_SLOW_PERIOD, int)
