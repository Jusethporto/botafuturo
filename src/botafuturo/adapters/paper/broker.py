"""`PaperBrokerAdapter`: production paper-trading `BrokerPort` implementation.

Simulates order placement and settlement entirely in memory -- no real
money, no external broker call. It honors the exact same contract
`tests.fakes.broker.FakeBroker` honors (see
`tests/contract/test_broker_port_contract.py`, which parametrizes over
both) and reuses the same domain logic (`resolve_outcome`, `pnl_for`) so
the two stay behaviorally identical.

`settle` never fetches a price itself: the caller supplies the
settlement price via the `expiry_quote` argument, per `BrokerPort`'s
documented signature. Fetching real quotes is a market-data-adapter
concern, out of scope here.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import ClassVar, Dict

from botafuturo.adapters.paper.balance import Balance
from botafuturo.domain.models import OrderAck, OrderRequest, Quote, Trade
from botafuturo.domain.pnl import pnl_for
from botafuturo.domain.settlement import resolve_outcome
from botafuturo.ports.broker import (
    SUPPORTED_EXPIRY_SECONDS,
    BrokerMode,
    InsufficientBalance,
    UnsupportedExpiry,
)

#: Simulated entry price for every placed order. Paper trading has no real
#: market feed at placement time; a real price feed is a later, separate
#: concern (a market-data adapter), not this order-execution simulator.
_PAPER_ENTRY_PRICE = Decimal("100")


class PaperBrokerAdapter:
    """In-memory `BrokerPort` implementation for paper trading."""

    MODE: ClassVar[BrokerMode] = BrokerMode.PAPER

    def __init__(self, starting_balance: Decimal) -> None:
        self._balance = Balance(starting_balance)
        self._next_id = 1
        self._settled: Dict[str, Trade] = {}

    def balance(self) -> Decimal:
        return self._balance.get()

    def place(self, order: OrderRequest) -> OrderAck:
        if order.stake <= 0 or order.stake > self._balance.get():
            raise InsufficientBalance(
                f"stake {order.stake} invalid for balance {self._balance.get()}"
            )
        if order.expiry_s not in SUPPORTED_EXPIRY_SECONDS:
            raise UnsupportedExpiry(f"expiry_s {order.expiry_s} is not supported")

        order_id = f"paper-order-{self._next_id}"
        self._next_id += 1
        self._balance.debit(order.stake)
        return OrderAck(
            order_id=order_id,
            request=order,
            expiry_at=order.opened_at + timedelta(seconds=order.expiry_s),
            entry_price=_PAPER_ENTRY_PRICE,
        )

    def settle(self, ack: OrderAck, expiry_quote: Quote) -> Trade:
        if ack.order_id in self._settled:
            return self._settled[ack.order_id]

        outcome = resolve_outcome(
            ack.request.direction, ack.entry_price, expiry_quote.price
        )
        pnl = pnl_for(outcome, ack.request.stake, ack.request.payout_rate)
        # `stake + pnl` uniformly credits back: stake+profit (WIN), 0
        # (LOSS, since pnl == -stake), or the refunded stake (TIE, pnl ==
        # 0). The stake itself was already debited in `place`.
        self._balance.credit(ack.request.stake + pnl)

        trade = Trade(
            ack=ack,
            expiry_price=expiry_quote.price,
            outcome=outcome,
            pnl=pnl,
            balance_after=self._balance.get(),
        )
        self._settled[ack.order_id] = trade
        return trade
