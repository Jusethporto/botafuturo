"""`BrokerPort`: order placement and settlement against a trading account.

v1 ships paper-trading only (`BrokerMode.PAPER`) -- the `BrokerMode` enum
exists to make a future live-trading mode an explicit, additive change
rather than a stringly-typed flag threaded through call sites.
"""
from __future__ import annotations

from decimal import Decimal
from enum import StrEnum, unique
from typing import ClassVar, Protocol, runtime_checkable

from botafuturo.domain.models import OrderAck, OrderRequest, Quote, Trade

#: Expiry durations (seconds) every `BrokerPort` implementation must support.
SUPPORTED_EXPIRY_SECONDS = frozenset({60, 300})


@unique
class BrokerMode(StrEnum):
    """Operating mode of a `BrokerPort` implementation.

    v1 has exactly one member: paper trading. A live-trading mode is a
    deliberately separate, future, additive change -- not added here.
    """

    PAPER = "paper"


class InsufficientBalance(Exception):
    """Raised by `BrokerPort.place` when `stake <= 0` or `stake > balance()`."""


class UnsupportedExpiry(Exception):
    """Raised by `BrokerPort.place` when `expiry_s` is not in
    `SUPPORTED_EXPIRY_SECONDS` (`{60, 300}`)."""


@runtime_checkable
class BrokerPort(Protocol):
    """A trading account: balance, order placement, and settlement."""

    MODE: ClassVar[BrokerMode]

    def balance(self) -> Decimal:
        """Return the current account balance."""
        ...

    def place(self, order: OrderRequest) -> OrderAck:
        """Place `order`, returning its acknowledgement.

        Raises:
            InsufficientBalance: if `order.stake <= 0` or
                `order.stake > self.balance()`.
            UnsupportedExpiry: if `order.expiry_s` is not one of
                `SUPPORTED_EXPIRY_SECONDS`.
        """
        ...

    def settle(self, ack: OrderAck, expiry_quote: Quote) -> Trade:
        """Settle `ack` against `expiry_quote`, returning the resulting `Trade`.

        Idempotent per `ack.order_id`: calling `settle` twice with the same
        `ack` returns an equal `Trade` and must not double-charge or
        double-credit the account balance.
        """
        ...
