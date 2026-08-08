"""Unit tests for `PaperBrokerAdapter`: production paper-trading broker.

Complements `tests/contract/test_broker_port_contract.py` (which proves
port conformance) with adapter-specific arithmetic and idempotency
assertions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from botafuturo.adapters.paper.broker import PaperBrokerAdapter
from botafuturo.domain.models import Direction, OrderRequest, Quote
from botafuturo.ports.broker import InsufficientBalance, UnsupportedExpiry

_ASSET = "EURUSD"
_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
_STAKE = Decimal("10")
_PAYOUT_RATE = Decimal("0.85")


def _order(stake: Decimal = _STAKE, expiry_s: int = 60) -> OrderRequest:
    return OrderRequest(
        asset=_ASSET,
        direction=Direction.CALL,
        stake=stake,
        expiry_s=expiry_s,
        opened_at=_T0,
        payout_rate=_PAYOUT_RATE,
    )


def _make_broker(starting_balance: Decimal = Decimal("1000")) -> PaperBrokerAdapter:
    return PaperBrokerAdapter(starting_balance=starting_balance)


def test_place_debits_stake_from_balance() -> None:
    broker = _make_broker()
    balance_before = broker.balance()
    broker.place(_order())
    assert broker.balance() == balance_before - _STAKE


def test_settle_win_nets_stake_times_payout_rate_gain() -> None:
    broker = _make_broker()
    balance_before = broker.balance()
    ack = broker.place(_order())
    winning_quote = Quote(
        asset=_ASSET, ts=ack.expiry_at, price=ack.entry_price + Decimal("1")
    )

    trade = broker.settle(ack, winning_quote)

    assert trade.pnl == Decimal("8.50")
    assert broker.balance() == balance_before + Decimal("8.50")


def test_settle_loss_nets_full_stake_loss() -> None:
    broker = _make_broker()
    balance_before = broker.balance()
    ack = broker.place(_order())
    losing_quote = Quote(
        asset=_ASSET, ts=ack.expiry_at, price=ack.entry_price - Decimal("1")
    )

    trade = broker.settle(ack, losing_quote)

    assert trade.pnl == Decimal("-10.00")
    assert broker.balance() == balance_before - Decimal("10.00")


def test_settle_tie_nets_zero_change() -> None:
    broker = _make_broker()
    balance_before = broker.balance()
    ack = broker.place(_order())
    tie_quote = Quote(asset=_ASSET, ts=ack.expiry_at, price=ack.entry_price)

    trade = broker.settle(ack, tie_quote)

    assert trade.pnl == Decimal("0")
    assert broker.balance() == balance_before


def test_settle_is_idempotent_same_trade_and_balance() -> None:
    broker = _make_broker()
    ack = broker.place(_order())
    quote = Quote(
        asset=_ASSET, ts=ack.expiry_at, price=ack.entry_price + Decimal("1")
    )

    first = broker.settle(ack, quote)
    balance_after_first = broker.balance()
    second = broker.settle(ack, quote)
    balance_after_second = broker.balance()

    assert second == first
    assert balance_after_second == balance_after_first


def test_place_raises_insufficient_balance_for_zero_stake() -> None:
    broker = _make_broker()
    with pytest.raises(InsufficientBalance):
        broker.place(_order(stake=Decimal("0")))


def test_place_raises_insufficient_balance_when_stake_exceeds_balance() -> None:
    broker = _make_broker(starting_balance=Decimal("5"))
    with pytest.raises(InsufficientBalance):
        broker.place(_order(stake=Decimal("10")))


def test_place_raises_unsupported_expiry() -> None:
    broker = _make_broker()
    with pytest.raises(UnsupportedExpiry):
        broker.place(_order(expiry_s=30))
