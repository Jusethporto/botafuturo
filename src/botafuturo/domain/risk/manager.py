"""`RiskManager`: a per-session circuit breaker over trade outcomes.

Tracks running daily P&L and the current consecutive-loss streak. Once
halted (daily loss limit or consecutive-loss limit breached), the
instance is permanently halted for its lifetime -- there is no resume
method. A new session requires a new `RiskManager` instance.
"""
from __future__ import annotations

from decimal import Decimal
from enum import Enum, unique
from typing import Optional, Tuple

from botafuturo.domain.models import Outcome, Trade


@unique
class RiskState(Enum):
    """Current gating state of a `RiskManager` instance."""

    ACTIVE = "active"
    HALTED = "halted"


@unique
class HaltReason(Enum):
    """Why a `RiskManager` halted (or why a single `can_open` call was denied)."""

    MAX_DAILY_LOSS = "max_daily_loss"
    MAX_CONSECUTIVE_LOSSES = "max_consecutive_losses"
    INSUFFICIENT_BALANCE = "insufficient_balance"


class RiskManager:
    """Circuit breaker: halts new positions once risk limits are breached."""

    def __init__(
        self,
        day_start_balance: Decimal,
        max_daily_loss_pct: Decimal = Decimal("0.05"),
        max_consecutive_losses: int = 5,
    ) -> None:
        self.day_start_balance = day_start_balance
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_consecutive_losses = max_consecutive_losses

        self._state = RiskState.ACTIVE
        self._halt_reason: Optional[HaltReason] = None
        self._daily_pnl = Decimal("0")
        self._consecutive_losses = 0

    @property
    def state(self) -> RiskState:
        return self._state

    @property
    def halt_reason(self) -> Optional[HaltReason]:
        return self._halt_reason

    def can_open(
        self, stake: Decimal, current_balance: Decimal
    ) -> Tuple[bool, Optional[HaltReason]]:
        """Whether a new position may be opened right now.

        A stake exceeding the current balance is reported as
        `INSUFFICIENT_BALANCE` for this call only -- it does not halt the
        instance's state (the caller may retry with a smaller stake).
        """
        if self._state is RiskState.HALTED:
            return False, self._halt_reason
        if stake > current_balance:
            return False, HaltReason.INSUFFICIENT_BALANCE
        return True, None

    def record(self, trade: Trade) -> None:
        """Record a settled trade's outcome, possibly triggering a halt."""
        self._daily_pnl += trade.pnl

        if trade.outcome is Outcome.WIN:
            self._consecutive_losses = 0
        elif trade.outcome is Outcome.LOSS:
            self._consecutive_losses += 1
        # TIE leaves the consecutive-loss streak unchanged.

        if self._state is RiskState.HALTED:
            return

        daily_loss_limit = -self.max_daily_loss_pct * self.day_start_balance
        if self._daily_pnl <= daily_loss_limit:
            self._state = RiskState.HALTED
            self._halt_reason = HaltReason.MAX_DAILY_LOSS
        elif self._consecutive_losses >= self.max_consecutive_losses:
            self._state = RiskState.HALTED
            self._halt_reason = HaltReason.MAX_CONSECUTIVE_LOSSES
