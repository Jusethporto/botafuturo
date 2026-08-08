"""`FakeMarketData`: a `MarketDataPort` fake backed by preloaded candles/quotes."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterator, List, Optional, Set

from botafuturo.domain.models import Candle, Quote
from botafuturo.ports.market_data import GapMarker, PriceUnavailable


class FakeMarketData:
    """Replays a preloaded list of candles and a preloaded quote table.

    Test code preloads `candles` (used by both `history` and
    `stream_closed_candles`) and `quotes` (a `datetime -> Quote` lookup used
    by `price_at`). Call `inject_gap(index)` to make the candle at that
    index (in the preloaded list) be emitted as a `GapMarker` instead of a
    `Candle` by `stream_closed_candles` -- this is a fake-only
    fault-injection hook, not part of `MarketDataPort` itself.
    """

    def __init__(
        self,
        candles: Optional[List[Candle]] = None,
        quotes: Optional[Dict[datetime, Quote]] = None,
    ) -> None:
        self._candles: List[Candle] = list(candles or [])
        self._quotes: Dict[datetime, Quote] = dict(quotes or {})
        self._gap_indices: Set[int] = set()
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def history(self, asset: str, timeframe_s: int, count: int) -> List[Candle]:
        matching = [
            c for c in self._candles if c.asset == asset and c.timeframe_s == timeframe_s
        ]
        return matching[-count:]

    def inject_gap(self, index: int) -> None:
        """Mark the candle at `index` (in the preloaded list) to be emitted
        as a `GapMarker` instead of a `Candle` by `stream_closed_candles`."""
        self._gap_indices.add(index)

    def stream_closed_candles(
        self, asset: str, timeframe_s: int
    ) -> Iterator[Candle | GapMarker]:
        for index, candle in enumerate(self._candles):
            if candle.asset != asset or candle.timeframe_s != timeframe_s:
                continue
            if index in self._gap_indices:
                yield GapMarker(asset=asset, timeframe_s=timeframe_s, at=candle.open_time)
            else:
                yield candle

    def price_at(self, asset: str, at: datetime) -> Quote:
        quote = self._quotes.get(at)
        if quote is None or quote.asset != asset:
            raise PriceUnavailable(f"no quote for {asset!r} at {at!r}")
        return quote
