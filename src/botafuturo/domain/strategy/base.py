"""The `Strategy` protocol: the contract every trading strategy implements.

A `Strategy` is a pure decision function over a stream of candles. It holds
no I/O and no side effects other than its own internal rolling-window
state. Concrete strategies (e.g. moving-average crossover) implement this
protocol structurally -- no explicit inheritance is required.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from botafuturo.domain.models import Candle, Signal


@runtime_checkable
class Strategy(Protocol):
    """Structural contract for a candle-driven trading strategy."""

    name: str
    params: Mapping[str, Any]

    def warmup_bars(self) -> int:
        """Minimum number of candles required before signals can be emitted."""
        ...

    def on_candle(self, candle: Candle) -> Optional[Signal]:
        """Feed one new candle; return a `Signal` if one is emitted, else `None`."""
        ...

    def reset(self) -> None:
        """Clear all internal rolling-window state (e.g. on a feed gap)."""
        ...
