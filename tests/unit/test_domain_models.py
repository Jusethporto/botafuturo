"""Unit tests for core domain models (frozen dataclasses, Decimal-based).

These models are pure data carriers with no behavior beyond identity and
equality (dataclass-generated). Tests assert: construction, immutability
(frozen -> raises on mutation), and value equality semantics.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from botafuturo.domain.models import (
    Candle,
    Direction,
    OrderAck,
    OrderRequest,
    Outcome,
    Quote,
    Signal,
    Trade,
)


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


class TestCandle:
    def test_construction_and_field_values(self) -> None:
        candle = Candle(
            asset="EURUSD",
            open_time=_now(),
            open=Decimal("1.1000"),
            high=Decimal("1.1050"),
            low=Decimal("1.0950"),
            close=Decimal("1.1020"),
            volume=Decimal("1000"),
            timeframe_s=60,
        )
        assert candle.asset == "EURUSD"
        assert candle.close == Decimal("1.1020")
        assert candle.timeframe_s == 60

    def test_is_frozen(self) -> None:
        candle = Candle(
            asset="EURUSD",
            open_time=_now(),
            open=Decimal("1.1"),
            high=Decimal("1.1"),
            low=Decimal("1.1"),
            close=Decimal("1.1"),
            volume=Decimal("0"),
            timeframe_s=60,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            candle.close = Decimal("2.0")  # type: ignore[misc]


class TestQuote:
    def test_construction(self) -> None:
        quote = Quote(asset="EURUSD", ts=_now(), price=Decimal("1.1234"))
        assert quote.price == Decimal("1.1234")

    def test_is_frozen(self) -> None:
        quote = Quote(asset="EURUSD", ts=_now(), price=Decimal("1.0"))
        with pytest.raises(dataclasses.FrozenInstanceError):
            quote.price = Decimal("2.0")  # type: ignore[misc]


class TestSignal:
    def test_construction_with_call_direction(self) -> None:
        signal = Signal(
            asset="EURUSD",
            direction=Direction.CALL,
            emitted_at=_now(),
            strategy_name="ma_crossover",
        )
        assert signal.direction is Direction.CALL

    def test_construction_with_put_direction(self) -> None:
        signal = Signal(
            asset="EURUSD",
            direction=Direction.PUT,
            emitted_at=_now(),
            strategy_name="ma_crossover",
        )
        assert signal.direction is Direction.PUT


class TestOrderRequestAndAck:
    def test_order_request_construction(self) -> None:
        request = OrderRequest(
            asset="EURUSD",
            direction=Direction.CALL,
            stake=Decimal("10"),
            expiry_s=60,
            opened_at=_now(),
            payout_rate=Decimal("0.85"),
        )
        assert request.stake == Decimal("10")
        assert request.payout_rate == Decimal("0.85")

    def test_order_ack_wraps_request(self) -> None:
        request = OrderRequest(
            asset="EURUSD",
            direction=Direction.CALL,
            stake=Decimal("10"),
            expiry_s=60,
            opened_at=_now(),
            payout_rate=Decimal("0.85"),
        )
        ack = OrderAck(
            order_id="abc-123",
            request=request,
            expiry_at=_now(),
            entry_price=Decimal("1.1000"),
        )
        assert ack.order_id == "abc-123"
        assert ack.request is request
        assert ack.entry_price == Decimal("1.1000")


class TestTrade:
    def test_construction(self) -> None:
        request = OrderRequest(
            asset="EURUSD",
            direction=Direction.CALL,
            stake=Decimal("10"),
            expiry_s=60,
            opened_at=_now(),
            payout_rate=Decimal("0.85"),
        )
        ack = OrderAck(
            order_id="abc-123",
            request=request,
            expiry_at=_now(),
            entry_price=Decimal("1.1000"),
        )
        trade = Trade(
            ack=ack,
            expiry_price=Decimal("1.1050"),
            outcome=Outcome.WIN,
            pnl=Decimal("8.50"),
            balance_after=Decimal("108.50"),
        )
        assert trade.outcome is Outcome.WIN
        assert trade.pnl == Decimal("8.50")
        assert trade.balance_after == Decimal("108.50")

    def test_is_frozen(self) -> None:
        request = OrderRequest(
            asset="EURUSD",
            direction=Direction.PUT,
            stake=Decimal("10"),
            expiry_s=60,
            opened_at=_now(),
            payout_rate=Decimal("0.85"),
        )
        ack = OrderAck(
            order_id="abc-123",
            request=request,
            expiry_at=_now(),
            entry_price=Decimal("1.1000"),
        )
        trade = Trade(
            ack=ack,
            expiry_price=Decimal("1.0950"),
            outcome=Outcome.LOSS,
            pnl=Decimal("-10.00"),
            balance_after=Decimal("90.00"),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            trade.pnl = Decimal("0")  # type: ignore[misc]
