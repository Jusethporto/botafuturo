"""`FakeBroker`: a `BrokerPort` fake tracking balance in memory.

Honors the same contract real `BrokerPort` adapters must honor
(`InsufficientBalance`, `UnsupportedExpiry`, idempotent `settle`) -- see
`tests/contract/test_broker_port_contract.py`, which runs against this fake
today and will run against `PaperBrokerAdapter` once it lands (a later PR).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import ClassVar, Dict

from botafuturo.domain.models import OrderAck, OrderRequest, Quote, Trade
from botafuturo.domain.pnl import pnl_for
from botafuturo.domain.settlement import resolve_outcome
from botafuturo.ports.broker import (
    SUPPORTED_EXPIRY_SECONDS,
    BrokerMode,
    InsufficientBalance,
    UnsupportedExpiry,
)

_FAKE_ENTRY_PRICE = Decimal("100")


class FakeBroker:
    """In-memory `BrokerPort` fake: tracks balance, honors the port contract."""

    MODE: ClassVar[BrokerMode] = BrokerMode.PAPER

    def __init__(self, starting_balance: Decimal) -> None:
        self._balance = starting_balance
        self._next_id = 1
        self._settled: Dict[str, Trade] = {}

    def balance(self) -> Decimal:
        return self._balance

    def place(self, order: OrderRequest) -> OrderAck:
        if order.stake <= 0 or order.stake > self._balance:
            raise InsufficientBalance(
                f"stake {order.stake} invalid for balance {self._balance}"
            )
        if order.expiry_s not in SUPPORTED_EXPIRY_SECONDS:
            raise UnsupportedExpiry(f"expiry_s {order.expiry_s} is not supported")

        order_id = f"fake-order-{self._next_id}"
        self._next_id += 1
        self._balance -= order.stake
        return OrderAck(
            order_id=order_id,
            request=order,
            expiry_at=order.opened_at + timedelta(seconds=order.expiry_s),
            entry_price=_FAKE_ENTRY_PRICE,
        )

    def settle(self, ack: OrderAck, expiry_quote: Quote) -> Trade:
        if ack.order_id in self._settled:
            return self._settled[ack.order_id]

        outcome = resolve_outcome(ack.request.direction, ack.entry_price, expiry_quote.price)
        pnl = pnl_for(outcome, ack.request.stake, ack.request.payout_rate)
        # `stake + pnl` uniformly returns: stake+profit (WIN), 0 (LOSS,
        # since pnl == -stake), or the refunded stake (TIE, pnl == 0). The
        # stake itself was already deducted from balance in `place`.
        self._balance += ack.request.stake + pnl

        trade = Trade(
            ack=ack,
            expiry_price=expiry_quote.price,
            outcome=outcome,
            pnl=pnl,
            balance_after=self._balance,
        )
        self._settled[ack.order_id] = trade
        return trade
