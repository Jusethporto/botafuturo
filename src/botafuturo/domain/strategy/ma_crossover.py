"""Moving-average crossover strategy.

Emits a CALL signal when the fast SMA crosses above the slow SMA, a PUT
signal when it crosses below, and `None` otherwise (including whenever
there is not yet enough history). Purely a function of the candles fed to
it -- no I/O, no wall-clock reads -- so replaying an identical candle
sequence through two fresh instances always yields an identical signal
sequence.
"""
from __future__ import annotations

from collections import deque
from decimal import Decimal
from typing import Any, Deque, List, Mapping, Optional

from botafuturo.domain.models import Candle, Direction, Signal


class MovingAverageCrossoverStrategy:
    """SMA(fast) / SMA(slow) crossover strategy."""

    name = "ma_crossover"

    def __init__(self, fast_period: int = 5, slow_period: int = 20) -> None:
        if fast_period <= 0 or slow_period <= 0:
            raise ValueError("fast_period and slow_period must be positive")
        if fast_period >= slow_period:
            raise ValueError("fast_period must be strictly less than slow_period")

        self.fast_period = fast_period
        self.slow_period = slow_period
        self.params: Mapping[str, Any] = {
            "fast_period": fast_period,
            "slow_period": slow_period,
        }
        self._closes: Deque[Decimal] = deque(maxlen=slow_period + 1)

    def warmup_bars(self) -> int:
        return self.slow_period + 1

    def on_candle(self, candle: Candle) -> Optional[Signal]:
        self._closes.append(candle.close)
        if len(self._closes) < self.warmup_bars():
            return None

        closes = list(self._closes)
        curr_fast = self._mean(closes[-self.fast_period :])
        curr_slow = self._mean(closes[1:])
        prev_fast = self._mean(closes[-self.fast_period - 1 : -1])
        prev_slow = self._mean(closes[:-1])

        if prev_fast <= prev_slow and curr_fast > curr_slow:
            direction = Direction.CALL
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            direction = Direction.PUT
        else:
            return None

        return Signal(
            asset=candle.asset,
            direction=direction,
            emitted_at=candle.open_time,
            strategy_name=self.name,
        )

    def reset(self) -> None:
        self._closes.clear()

    @staticmethod
    def _mean(values: List[Decimal]) -> Decimal:
        return sum(values, Decimal(0)) / Decimal(len(values))
