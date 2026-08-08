"""Unit tests for `MovingAverageCrossoverStrategy`.

Uses small `fast_period`/`slow_period` values (2/3) instead of the
production defaults (5/20) so crossover scenarios can be expressed with a
handful of candles. The strategy must stay pure/deterministic: no network
or file I/O, and no wall-clock dependency (signal `emitted_at` derives
from the candle being processed).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from botafuturo.domain.models import Candle, Direction, Signal
from botafuturo.domain.strategy.ma_crossover import MovingAverageCrossoverStrategy

_START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _candle(index: int, close: str) -> Candle:
    return Candle(
        asset="EURUSD",
        open_time=_START + timedelta(minutes=index),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("100"),
        timeframe_s=60,
    )


def _feed(strategy: MovingAverageCrossoverStrategy, closes: list[str]) -> list[Optional[Signal]]:
    return [strategy.on_candle(_candle(i, close)) for i, close in enumerate(closes)]


class TestWarmup:
    def test_warmup_bars_equals_slow_period_plus_one(self) -> None:
        strategy = MovingAverageCrossoverStrategy(fast_period=2, slow_period=3)
        assert strategy.warmup_bars() == 4

    def test_insufficient_history_emits_none(self) -> None:
        strategy = MovingAverageCrossoverStrategy(fast_period=2, slow_period=3)
        signals = _feed(strategy, ["10", "10", "10"])
        assert signals == [None, None, None]

    def test_default_periods(self) -> None:
        strategy = MovingAverageCrossoverStrategy()
        assert strategy.fast_period == 5
        assert strategy.slow_period == 20
        assert strategy.warmup_bars() == 21


class TestCrossoverDetection:
    def test_bullish_crossover_emits_call(self) -> None:
        strategy = MovingAverageCrossoverStrategy(fast_period=2, slow_period=3)
        signals = _feed(strategy, ["10", "10", "10", "10", "12"])
        assert signals[:4] == [None, None, None, None]
        assert signals[4] is not None
        assert signals[4].direction is Direction.CALL
        assert signals[4].strategy_name == "ma_crossover"
        assert signals[4].asset == "EURUSD"

    def test_bearish_crossover_emits_put(self) -> None:
        strategy = MovingAverageCrossoverStrategy(fast_period=2, slow_period=3)
        signals = _feed(strategy, ["10", "10", "10", "10", "8"])
        assert signals[4] is not None
        assert signals[4].direction is Direction.PUT

    def test_no_crossover_when_flat_emits_none(self) -> None:
        strategy = MovingAverageCrossoverStrategy(fast_period=2, slow_period=3)
        signals = _feed(strategy, ["10", "10", "10", "10", "10", "10"])
        assert all(signal is None for signal in signals)


class TestResetAndDeterminism:
    def test_reset_clears_internal_state(self) -> None:
        strategy = MovingAverageCrossoverStrategy(fast_period=2, slow_period=3)
        _feed(strategy, ["10", "10", "10", "10", "12"])
        strategy.reset()
        # After reset, history is gone: feeding fewer than warmup_bars again
        # must emit None, proving no leftover state from before the reset.
        signals = _feed(strategy, ["10", "10", "10"])
        assert signals == [None, None, None]

    def test_replay_determinism_across_fresh_instances(self) -> None:
        closes = ["10", "10", "10", "10", "12", "14", "14", "13", "11", "9"]

        strategy_a = MovingAverageCrossoverStrategy(fast_period=2, slow_period=3)
        strategy_b = MovingAverageCrossoverStrategy(fast_period=2, slow_period=3)

        signals_a = _feed(strategy_a, closes)
        signals_b = _feed(strategy_b, closes)

        directions_a = [s.direction if s is not None else None for s in signals_a]
        directions_b = [s.direction if s is not None else None for s in signals_b]
        timestamps_a = [s.emitted_at if s is not None else None for s in signals_a]
        timestamps_b = [s.emitted_at if s is not None else None for s in signals_b]

        assert directions_a == directions_b
        assert timestamps_a == timestamps_b


class TestConstructorValidation:
    def test_fast_period_must_be_less_than_slow_period(self) -> None:
        import pytest

        with pytest.raises(ValueError):
            MovingAverageCrossoverStrategy(fast_period=20, slow_period=5)
