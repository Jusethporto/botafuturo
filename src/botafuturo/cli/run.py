"""Session-driving loop: streams closed candles from a `MarketDataPort` into
a `TradingSession`.

This module owns exactly one responsibility: connect, drive, disconnect --
it never constructs a `MarketDataPort` or a `TradingSession` itself (that is
`cli/wire.py`'s job as the composition root). It is fully testable offline
against `tests.fakes.market_data.FakeMarketData`'s finite, preloaded candle
list; a live feed (a future real Exnova adapter) would simply yield
indefinitely instead of terminating, without requiring any change here.
"""
from __future__ import annotations

import logging

from botafuturo.domain.session import TradingSession
from botafuturo.ports.market_data import GapMarker, MarketDataPort

logger = logging.getLogger(__name__)


def run_session(
    session: TradingSession,
    market_data: MarketDataPort,
    asset: str,
    timeframe_s: int,
) -> int:
    """Drive `session` from `market_data`'s closed-candle stream until it ends.

    Connects `market_data`, feeds every closed `Candle` for `asset`/
    `timeframe_s` to `session.on_candle`, and disconnects once the stream is
    exhausted (via a `finally`, so a mid-stream exception still disconnects).

    A `GapMarker` is never fed to `session.on_candle` -- a feed gap means
    the strategy's accumulated rolling-window state is no longer
    trustworthy, so `session.strategy.reset()` is called instead and the
    gap slot is otherwise skipped.

    Returns the number of `Candle`s actually processed (excluding gaps), so
    callers/tests can assert the loop did real work.
    """
    market_data.connect()
    processed = 0
    try:
        for item in market_data.stream_closed_candles(asset, timeframe_s):
            if isinstance(item, GapMarker):
                logger.warning(
                    "market data gap for %s @ %ss at %s (reason=%s); resetting strategy",
                    asset,
                    timeframe_s,
                    item.at,
                    item.reason,
                )
                session.strategy.reset()
                continue
            session.on_candle(item)
            processed += 1
    finally:
        market_data.disconnect()
    return processed
