"""Unit tests for `FrozenClock`'s fake-only manual-advance API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tests.fakes.clock import FrozenClock

_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_tick_advances_now_by_delta() -> None:
    clock = FrozenClock(_T0)
    clock.tick(timedelta(seconds=90))
    assert clock.now() == _T0 + timedelta(seconds=90)


def test_set_jumps_now_directly() -> None:
    clock = FrozenClock(_T0)
    target = datetime(2027, 6, 1, tzinfo=timezone.utc)
    clock.set(target)
    assert clock.now() == target
