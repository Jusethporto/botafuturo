"""Unit tests for `RiskManager`.

`RiskManager` only reads `trade.outcome` and `trade.pnl` from `Trade`
instances, so the helper below builds minimal-but-valid `Trade` objects
(the nested `OrderAck`/`OrderRequest` values are irrelevant placeholders).
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from botafuturo.domain.models import (
    Direction,
    OrderAck,
    OrderRequest,
    Outcome,
    Trade,
)
from botafuturo.domain.risk.manager import HaltReason, RiskManager, RiskState

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _trade(outcome: Outcome, pnl: str, balance_after: str = "0") -> Trade:
    request = OrderRequest(
        asset="EURUSD",
        direction=Direction.CALL,
        stake=Decimal("10"),
        expiry_s=60,
        opened_at=_NOW,
        payout_rate=Decimal("0.85"),
    )
    ack = OrderAck(
        order_id="order-1",
        request=request,
        expiry_at=_NOW,
        entry_price=Decimal("1.1000"),
    )
    return Trade(
        ack=ack,
        expiry_price=Decimal("1.1000"),
        outcome=outcome,
        pnl=Decimal(pnl),
        balance_after=Decimal(balance_after),
    )


class TestInitialState:
    def test_starts_active(self) -> None:
        manager = RiskManager(day_start_balance=Decimal("1000"))
        assert manager.state is RiskState.ACTIVE
        assert manager.halt_reason is None


class TestCanOpen:
    def test_allows_open_when_active_and_sufficient_balance(self) -> None:
        manager = RiskManager(day_start_balance=Decimal("1000"))
        allowed, reason = manager.can_open(Decimal("10"), Decimal("1000"))
        assert allowed is True
        assert reason is None

    def test_denies_when_stake_exceeds_balance(self) -> None:
        manager = RiskManager(day_start_balance=Decimal("1000"))
        allowed, reason = manager.can_open(Decimal("100"), Decimal("50"))
        assert allowed is False
        assert reason is HaltReason.INSUFFICIENT_BALANCE
        # Insufficient-balance check must not halt the instance's state.
        assert manager.state is RiskState.ACTIVE

    def test_denies_when_already_halted(self) -> None:
        manager = RiskManager(
            day_start_balance=Decimal("100"), max_daily_loss_pct=Decimal("0.05")
        )
        manager.record(_trade(Outcome.LOSS, "-10"))
        assert manager.state is RiskState.HALTED

        allowed, reason = manager.can_open(Decimal("1"), Decimal("1000"))
        assert allowed is False
        assert reason is manager.halt_reason


class TestDailyLossHalt:
    def test_daily_loss_threshold_trips_halt(self) -> None:
        manager = RiskManager(
            day_start_balance=Decimal("100"), max_daily_loss_pct=Decimal("0.05")
        )
        manager.record(_trade(Outcome.LOSS, "-6"))
        assert manager.state is RiskState.HALTED
        assert manager.halt_reason is HaltReason.MAX_DAILY_LOSS

    def test_below_threshold_stays_active(self) -> None:
        manager = RiskManager(
            day_start_balance=Decimal("100"), max_daily_loss_pct=Decimal("0.05")
        )
        manager.record(_trade(Outcome.LOSS, "-4"))
        assert manager.state is RiskState.ACTIVE
        assert manager.halt_reason is None


class TestConsecutiveLossHalt:
    def test_fourth_consecutive_loss_stays_active(self) -> None:
        manager = RiskManager(
            day_start_balance=Decimal("10000"), max_consecutive_losses=5
        )
        for _ in range(4):
            manager.record(_trade(Outcome.LOSS, "-1"))
        assert manager.state is RiskState.ACTIVE

    def test_fifth_consecutive_loss_trips_halt(self) -> None:
        manager = RiskManager(
            day_start_balance=Decimal("10000"), max_consecutive_losses=5
        )
        for _ in range(5):
            manager.record(_trade(Outcome.LOSS, "-1"))
        assert manager.state is RiskState.HALTED
        assert manager.halt_reason is HaltReason.MAX_CONSECUTIVE_LOSSES

    def test_win_resets_consecutive_counter(self) -> None:
        manager = RiskManager(
            day_start_balance=Decimal("10000"), max_consecutive_losses=5
        )
        for _ in range(4):
            manager.record(_trade(Outcome.LOSS, "-1"))
        manager.record(_trade(Outcome.WIN, "1"))
        for _ in range(4):
            manager.record(_trade(Outcome.LOSS, "-1"))
        # Only 4 consecutive losses since the WIN reset the streak.
        assert manager.state is RiskState.ACTIVE

        manager.record(_trade(Outcome.LOSS, "-1"))
        assert manager.state is RiskState.HALTED
        assert manager.halt_reason is HaltReason.MAX_CONSECUTIVE_LOSSES

    def test_tie_does_not_change_consecutive_counter(self) -> None:
        manager = RiskManager(
            day_start_balance=Decimal("10000"), max_consecutive_losses=5
        )
        for _ in range(4):
            manager.record(_trade(Outcome.LOSS, "-1"))
        manager.record(_trade(Outcome.TIE, "0"))
        assert manager.state is RiskState.ACTIVE

        # The streak is still 4 (TIE did not reset or increment it), so
        # exactly one more loss should trip the halt.
        manager.record(_trade(Outcome.LOSS, "-1"))
        assert manager.state is RiskState.HALTED
        assert manager.halt_reason is HaltReason.MAX_CONSECUTIVE_LOSSES


class TestTerminalHalt:
    def test_halted_state_is_terminal(self) -> None:
        manager = RiskManager(
            day_start_balance=Decimal("100"), max_daily_loss_pct=Decimal("0.05")
        )
        manager.record(_trade(Outcome.LOSS, "-6"))
        assert manager.state is RiskState.HALTED

        manager.record(_trade(Outcome.WIN, "50"))
        assert manager.state is RiskState.HALTED
        assert not hasattr(manager, "resume")
