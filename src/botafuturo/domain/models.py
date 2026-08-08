"""Core domain entities.

All models are frozen (immutable) dataclasses. Money and price fields use
`Decimal` exclusively -- floats are never used for anything that touches
value calculations, to avoid binary floating-point rounding error in
financial arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum, unique


@unique
class Direction(Enum):
    """Direction of a binary-option trade."""

    CALL = "call"
    PUT = "put"


@unique
class Outcome(Enum):
    """Settlement outcome of a closed trade."""

    WIN = "win"
    LOSS = "loss"
    TIE = "tie"


@dataclass(frozen=True, slots=True)
class Candle:
    """A single OHLCV candle for an asset over a fixed timeframe."""

    asset: str
    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    timeframe_s: int


@dataclass(frozen=True, slots=True)
class Quote:
    """A single point-in-time price observation for an asset."""

    asset: str
    ts: datetime
    price: Decimal


@dataclass(frozen=True, slots=True)
class Signal:
    """A trading signal emitted by a strategy."""

    asset: str
    direction: Direction
    emitted_at: datetime
    strategy_name: str


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """A request to open a binary-option position."""

    asset: str
    direction: Direction
    stake: Decimal
    expiry_s: int
    opened_at: datetime
    payout_rate: Decimal


@dataclass(frozen=True, slots=True)
class OrderAck:
    """Broker acknowledgement of an opened position."""

    order_id: str
    request: OrderRequest
    expiry_at: datetime
    entry_price: Decimal


@dataclass(frozen=True, slots=True)
class Trade:
    """A closed (settled) trade, including its P&L outcome."""

    ack: OrderAck
    expiry_price: Decimal
    outcome: Outcome
    pnl: Decimal
    balance_after: Decimal
