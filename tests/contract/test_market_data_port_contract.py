"""Conformance tests for `MarketDataPort` implementations.

Parametrized over every known FULLY-CONFORMING implementation of
`MarketDataPort`. Today that is only `FakeMarketData`.

`ExnovaMarketDataAdapter` (PR10 / Phase 8) deliberately does NOT join
`MARKET_DATA_FACTORIES`: its `history()`/`price_at()` intentionally raise
`NotImplementedError` in v1 (see `adapters/exnova/market_data.py`'s module
docstring -- the `get-candles` schema needed for `history()` was not
captured with enough confidence during the validation spike). This
suite's `history`/`price_at` tests assert real, successful behavior for
every factory in the list, so adding a factory whose `history`/`price_at`
always raise would either force those shared tests to special-case it
(weakening `FakeMarketData`'s own coverage) or fail outright -- neither is
acceptable. `ExnovaMarketDataAdapter`'s narrower, real coverage instead
lives in `tests/integration/test_exnova_market_data_adapter.py`
(`stream_closed_candles`/`connect`/`disconnect`, against a fake WS
transport) plus its explicit `NotImplementedError` assertions for
`history`/`price_at`. `test_conforms_to_protocol_shape`-style structural
checks are satisfied there too; this file's parametrized suite is reserved
for implementations that honor the FULL contract.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from botafuturo.domain.models import Candle, Quote
from botafuturo.ports.market_data import GapMarker, MarketDataPort, PriceUnavailable
from tests.fakes.market_data import FakeMarketData

_ASSET = "EURUSD"
_TIMEFRAME_S = 60
_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _candle(open_time: datetime, close: str) -> Candle:
    return Candle(
        asset=_ASSET,
        open_time=open_time,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("10"),
        timeframe_s=_TIMEFRAME_S,
    )


def _make_market_data() -> FakeMarketData:
    candles = [
        _candle(_T0 + timedelta(seconds=i * _TIMEFRAME_S), str(100 + i)) for i in range(5)
    ]
    quotes = {_T0: Quote(asset=_ASSET, ts=_T0, price=Decimal("100"))}
    return FakeMarketData(candles=candles, quotes=quotes)


MARKET_DATA_FACTORIES = [pytest.param(_make_market_data, id="FakeMarketData")]


@pytest.mark.contract
class TestMarketDataPortContract:
    @pytest.mark.parametrize("make", MARKET_DATA_FACTORIES)
    def test_conforms_to_protocol_shape(self, make) -> None:
        market_data = make()
        assert isinstance(market_data, MarketDataPort)

    @pytest.mark.parametrize("make", MARKET_DATA_FACTORIES)
    def test_history_returns_requested_count_most_recent_slice(self, make) -> None:
        market_data = make()
        result = market_data.history(_ASSET, _TIMEFRAME_S, count=2)
        assert [c.close for c in result] == [Decimal("103"), Decimal("104")]

    @pytest.mark.parametrize("make", MARKET_DATA_FACTORIES)
    def test_history_returns_fewer_than_count_when_not_enough_candles(self, make) -> None:
        market_data = make()
        result = market_data.history(_ASSET, _TIMEFRAME_S, count=100)
        assert len(result) == 5

    @pytest.mark.parametrize("make", MARKET_DATA_FACTORIES)
    def test_price_at_returns_quote_for_known_timestamp(self, make) -> None:
        market_data = make()
        quote = market_data.price_at(_ASSET, _T0)
        assert quote.price == Decimal("100")

    @pytest.mark.parametrize("make", MARKET_DATA_FACTORIES)
    def test_price_at_raises_price_unavailable_for_unknown_timestamp(self, make) -> None:
        market_data = make()
        with pytest.raises(PriceUnavailable):
            market_data.price_at(_ASSET, _T0.replace(year=2099))

    @pytest.mark.parametrize("make", MARKET_DATA_FACTORIES)
    def test_stream_closed_candles_yields_candles_in_order(self, make) -> None:
        market_data = make()
        streamed = list(market_data.stream_closed_candles(_ASSET, _TIMEFRAME_S))
        assert len(streamed) == 5
        assert all(isinstance(item, Candle) for item in streamed)
        assert [c.close for c in streamed] == [Decimal(str(100 + i)) for i in range(5)]

    @pytest.mark.parametrize("make", MARKET_DATA_FACTORIES)
    def test_stream_closed_candles_can_emit_gap_marker(self, make) -> None:
        market_data = make()
        inject_gap = getattr(market_data, "inject_gap", None)
        if inject_gap is None:
            pytest.skip("implementation has no fault-injection hook")
        inject_gap(2)

        streamed = list(market_data.stream_closed_candles(_ASSET, _TIMEFRAME_S))

        assert isinstance(streamed[2], GapMarker)
        assert streamed[2].asset == _ASSET
        assert streamed[2].timeframe_s == _TIMEFRAME_S
        assert all(isinstance(item, Candle) for i, item in enumerate(streamed) if i != 2)
