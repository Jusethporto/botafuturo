"""Profit-and-loss calculation for a settled binary-option trade."""
from __future__ import annotations

from decimal import Decimal

from botafuturo.domain.models import Outcome


def pnl_for(outcome: Outcome, stake: Decimal, payout_rate: Decimal) -> Decimal:
    """Compute the P&L for a settled trade.

    WIN returns `stake * payout_rate` (the broker's profit payout, not
    including the returned stake). LOSS forfeits the full stake. TIE
    returns zero (stake is refunded, no gain/loss).
    """
    if outcome is Outcome.WIN:
        return stake * payout_rate
    if outcome is Outcome.LOSS:
        return -stake
    return Decimal("0")
