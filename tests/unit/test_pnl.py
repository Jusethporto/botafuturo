"""Unit tests for `pnl_for`: profit-and-loss calculation per outcome."""
from __future__ import annotations

from decimal import Decimal

from botafuturo.domain.models import Outcome
from botafuturo.domain.pnl import pnl_for

_STAKE = Decimal("10")
_PAYOUT_RATE = Decimal("0.85")


def test_win_pays_stake_times_payout_rate() -> None:
    assert pnl_for(Outcome.WIN, _STAKE, _PAYOUT_RATE) == Decimal("8.50")


def test_loss_forfeits_the_full_stake() -> None:
    assert pnl_for(Outcome.LOSS, _STAKE, _PAYOUT_RATE) == Decimal("-10.00")


def test_tie_returns_zero() -> None:
    assert pnl_for(Outcome.TIE, _STAKE, _PAYOUT_RATE) == Decimal("0")
