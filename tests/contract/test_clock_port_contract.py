"""Conformance test for `ClockPort` implementations.

Parametrized over every known implementation of `ClockPort`. Today that is
only `FrozenClock`; a real system-clock adapter (a later PR, if ever needed)
joins this same list once it exists.

Structural: `ClockPort` has a single method with exactly one possible
output shape (the current time). Triangulation skipped: purely structural,
no branching.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from botafuturo.ports.clock import ClockPort
from tests.fakes.clock import FrozenClock

_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

CLOCK_FACTORIES = [pytest.param(lambda: FrozenClock(_T0), id="FrozenClock")]


@pytest.mark.contract
class TestClockPortContract:
    @pytest.mark.parametrize("make", CLOCK_FACTORIES)
    def test_conforms_to_protocol_shape(self, make) -> None:
        clock = make()
        assert isinstance(clock, ClockPort)

    @pytest.mark.parametrize("make", CLOCK_FACTORIES)
    def test_now_returns_the_configured_time(self, make) -> None:
        clock = make()
        assert clock.now() == _T0
