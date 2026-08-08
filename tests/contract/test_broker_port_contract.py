"""Conformance tests for `BrokerPort` implementations.

Parametrized over every known implementation of `BrokerPort`. Today that is
only `FakeBroker`; `PaperBrokerAdapter` (a later PR) joins this same list
once it exists, so this same suite proves both conform to the port's
documented contract (`InsufficientBalance`, `UnsupportedExpiry`, and
idempotent `settle`).
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from botafuturo.domain.models import Direction, OrderRequest, Quote
from botafuturo.ports.broker import BrokerPort, InsufficientBalance, UnsupportedExpiry
from tests.fakes.broker import FakeBroker

_ASSET = "EURUSD"
_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _order(stake: Decimal = Decimal("10"), expiry_s: int = 60) -> OrderRequest:
    return OrderRequest(
        asset=_ASSET,
        direction=Direction.CALL,
        stake=stake,
        expiry_s=expiry_s,
        opened_at=_T0,
        payout_rate=Decimal("0.85"),
    )


def _make_broker() -> FakeBroker:
    return FakeBroker(starting_balance=Decimal("1000"))


BROKER_FACTORIES = [pytest.param(_make_broker, id="FakeBroker")]


@pytest.mark.contract
class TestBrokerPortContract:
    @pytest.mark.parametrize("make", BROKER_FACTORIES)
    def test_conforms_to_protocol_shape(self, make) -> None:
        broker = make()
        assert isinstance(broker, BrokerPort)

    @pytest.mark.parametrize("make", BROKER_FACTORIES)
    def test_place_raises_insufficient_balance_for_zero_stake(self, make) -> None:
        broker = make()
        with pytest.raises(InsufficientBalance):
            broker.place(_order(stake=Decimal("0")))

    @pytest.mark.parametrize("make", BROKER_FACTORIES)
    def test_place_raises_insufficient_balance_for_negative_stake(self, make) -> None:
        broker = make()
        with pytest.raises(InsufficientBalance):
            broker.place(_order(stake=Decimal("-5")))

    @pytest.mark.parametrize("make", BROKER_FACTORIES)
    def test_place_raises_insufficient_balance_when_stake_exceeds_balance(self, make) -> None:
        broker = make()
        with pytest.raises(InsufficientBalance):
            broker.place(_order(stake=Decimal("100000")))

    @pytest.mark.parametrize("make", BROKER_FACTORIES)
    def test_place_raises_unsupported_expiry(self, make) -> None:
        broker = make()
        with pytest.raises(UnsupportedExpiry):
            broker.place(_order(expiry_s=30))

    @pytest.mark.parametrize("make", BROKER_FACTORIES)
    def test_place_accepts_60_and_300_second_expiries(self, make) -> None:
        broker = make()
        ack_60 = broker.place(_order(expiry_s=60))
        ack_300 = broker.place(_order(expiry_s=300))
        assert ack_60.request.expiry_s == 60
        assert ack_300.request.expiry_s == 300

    @pytest.mark.parametrize("make", BROKER_FACTORIES)
    def test_place_deducts_stake_from_balance(self, make) -> None:
        broker = make()
        balance_before = broker.balance()
        broker.place(_order(stake=Decimal("10")))
        assert broker.balance() == balance_before - Decimal("10")

    @pytest.mark.parametrize("make", BROKER_FACTORIES)
    def test_settle_is_idempotent_per_order_id(self, make) -> None:
        broker = make()
        ack = broker.place(_order(stake=Decimal("10")))
        expiry_quote = Quote(
            asset=_ASSET, ts=ack.expiry_at, price=ack.entry_price + Decimal("5")
        )

        first = broker.settle(ack, expiry_quote)
        balance_after_first = broker.balance()
        second = broker.settle(ack, expiry_quote)
        balance_after_second = broker.balance()

        assert second == first
        assert balance_after_second == balance_after_first
