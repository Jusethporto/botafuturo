"""Conformance tests for `MarketDataPort` implementations.

Parametrized over every known implementation of `MarketDataPort`. Today
that is only `FakeMarketData`; `ExnovaMarketDataAdapter` (a later PR) joins
this same list once it exists, so this same suite proves both conform to
the port's documented contract.
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
