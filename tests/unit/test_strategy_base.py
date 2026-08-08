"""Unit tests for the `Strategy` protocol.

`Strategy` is a `typing.Protocol` -- it has no runtime behavior of its own.
These tests assert structural (duck-typed) conformance: any object that
implements the required attributes/methods satisfies `isinstance` checks
against the runtime-checkable protocol, and objects missing members do not.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from botafuturo.domain.models import Candle
from botafuturo.domain.strategy.base import Strategy


class _ConformingStrategy:
    name = "conforming"
    params: Mapping[str, Any] = {}

    def warmup_bars(self) -> int:
        return 1

    def on_candle(self, candle: Candle) -> None:
        return None

    def reset(self) -> None:
        return None


class _NonConformingStrategy:
    """Missing `reset` and `on_candle` -- should not satisfy the protocol."""

    name = "broken"
    params: Mapping[str, Any] = {}

    def warmup_bars(self) -> int:
        return 1


def test_conforming_object_satisfies_strategy_protocol() -> None:
    assert isinstance(_ConformingStrategy(), Strategy)


def test_non_conforming_object_does_not_satisfy_strategy_protocol() -> None:
    assert not isinstance(_NonConformingStrategy(), Strategy)


def test_conforming_strategy_callable_contract() -> None:
    strategy: Strategy = _ConformingStrategy()
    candle = Candle(
        asset="EURUSD",
        open_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        open=Decimal("1.1"),
        high=Decimal("1.1"),
        low=Decimal("1.1"),
        close=Decimal("1.1"),
        volume=Decimal("0"),
        timeframe_s=60,
    )
    assert strategy.warmup_bars() == 1
    assert strategy.on_candle(candle) is None
    assert strategy.reset() is None
