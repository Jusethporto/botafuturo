"""Unit tests for `cli/run.py` — the offline/online session-driving loop.

Exercised fully offline via `FakeMarketData`'s finite preloaded candle list,
so the loop terminates naturally -- no infinite-loop concerns in tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from botafuturo.cli.run import run_session
from botafuturo.domain.models import Candle, Signal
from botafuturo.domain.risk.manager import RiskManager
from botafuturo.domain.session import TradingSession
from botafuturo.domain.strategy.ma_crossover import MovingAverageCrossoverStrategy
from tests.fakes.market_data import FakeMarketData

_ASSET = "EURUSD"
_TIMEFRAME_S = 60
_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _candle(index: int, close: str) -> Candle:
    return Candle(
        asset=_ASSET,
        open_time=_T0 + timedelta(seconds=index * _TIMEFRAME_S),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("10"),
        timeframe_s=_TIMEFRAME_S,
    )


class _SpyStrategy:
    """Wraps a real strategy, counting `reset()` calls without changing behavior."""

    def __init__(self, inner: MovingAverageCrossoverStrategy) -> None:
        self._inner = inner
        self.name = inner.name
        self.params = inner.params
        self.reset_calls = 0

    def warmup_bars(self) -> int:
        return self._inner.warmup_bars()

    def on_candle(self, candle: Candle) -> Optional[Signal]:
        return self._inner.on_candle(candle)

    def reset(self) -> None:
        self.reset_calls += 1
        self._inner.reset()


def _build_session():
    strategy = _SpyStrategy(MovingAverageCrossoverStrategy(fast_period=2, slow_period=3))
    risk_manager = RiskManager(day_start_balance=Decimal("1000"))
    logged: List[object] = []

    def _open_position(request):
        raise AssertionError(
            "no signal expected: candle closes are flat, so no crossover fires"
        )

    def _settle_position(ack, quote):
        raise AssertionError(
            "no position expected to settle: no signal is ever emitted"
        )

    session = TradingSession(
        asset=_ASSET,
        strategy=strategy,
        risk_manager=risk_manager,
        stake=Decimal("10"),
        expiry_s=_TIMEFRAME_S,
        payout_rate=Decimal("0.85"),
        open_position=_open_position,
        get_balance=lambda: Decimal("1000"),
        settle_position=_settle_position,
        log_trade=logged.append,
    )
    return session, strategy


def test_run_session_processes_every_candle_and_disconnects_when_stream_ends() -> None:
    candles = [_candle(i, "100") for i in range(5)]
    market_data = FakeMarketData(candles=candles)
    session, _strategy = _build_session()

    processed = run_session(session, market_data, _ASSET, _TIMEFRAME_S)

    assert processed == 5
    assert market_data.connected is False


def test_run_session_connects_before_streaming() -> None:
    candles = [_candle(i, "100") for i in range(2)]

    connect_order: List[str] = []

    class _TrackingMarketData(FakeMarketData):
        def connect(self) -> None:
            connect_order.append("connect")
            super().connect()

        def stream_closed_candles(self, asset: str, timeframe_s: int):
            connect_order.append("stream")
            return super().stream_closed_candles(asset, timeframe_s)

    market_data = _TrackingMarketData(candles=candles)
    session, _strategy = _build_session()

    run_session(session, market_data, _ASSET, _TIMEFRAME_S)

    assert connect_order[0] == "connect"


def test_run_session_resets_strategy_on_gap_marker_and_skips_it() -> None:
    candles = [_candle(i, "100") for i in range(5)]
    market_data = FakeMarketData(candles=candles)
    market_data.inject_gap(2)
    session, strategy = _build_session()

    processed = run_session(session, market_data, _ASSET, _TIMEFRAME_S)

    assert processed == 4  # the gap slot is skipped, not fed to on_candle
    assert strategy.reset_calls == 1


def test_run_session_disconnects_even_when_stream_is_empty() -> None:
    market_data = FakeMarketData(candles=[])
    session, _strategy = _build_session()

    processed = run_session(session, market_data, _ASSET, _TIMEFRAME_S)

    assert processed == 0
    assert market_data.connected is False
