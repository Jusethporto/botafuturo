"""`MarketDataPort`: read-only access to market candles and quotes.

Adapters implementing this port (e.g. `ExnovaMarketDataAdapter`, landing in
a later PR) supply historical candles, a live stream of closed candles, and
point-in-time price lookups used to settle expired positions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Protocol, Sequence, runtime_checkable

from botafuturo.domain.models import Candle, Quote


@dataclass(frozen=True, slots=True)
class GapMarker:
    """Emitted by `stream_closed_candles` in place of a `Candle` when the
    underlying feed is known to have skipped one or more timeframe bars
    (e.g. a reconnect, provider outage, or maintenance window).

    Consumers (e.g. `TradingSession`) MUST treat a `GapMarker` as "no candle
    available for this slot" rather than silently substituting a candle --
    strategies must not warm up or emit signals across an unverified gap.
    """

    asset: str
    timeframe_s: int
    at: datetime
    reason: str = "unknown"


class PriceUnavailable(Exception):
    """Raised by `MarketDataPort.price_at` when no quote exists at `at`."""


@runtime_checkable
class MarketDataPort(Protocol):
    """Read-only market data source: connection lifecycle + candle/quote access."""

    def connect(self) -> None:
        """Establish the underlying connection/session. Idempotent."""
        ...

    def disconnect(self) -> None:
        """Tear down the underlying connection/session. Idempotent."""
        ...

    def history(self, asset: str, timeframe_s: int, count: int) -> Sequence[Candle]:
        """Return up to `count` most recent CLOSED candles, oldest first."""
        ...

    def stream_closed_candles(
        self, asset: str, timeframe_s: int
    ) -> Iterator[Candle | GapMarker]:
        """Yield closed candles as they become available, in order.

        Yields a `GapMarker` instead of a `Candle` for any timeframe slot
        the feed is known to have skipped.
        """
        ...

    def price_at(self, asset: str, at: datetime) -> Quote:
        """Return the quote for `asset` at time `at`.

        Raises:
            PriceUnavailable: if no quote exists at that time.
        """
        ...
