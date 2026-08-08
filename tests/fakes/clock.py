"""`FrozenClock`: a `ClockPort` fake with a fixed, manually-advanceable time."""
from __future__ import annotations

from datetime import datetime, timedelta


class FrozenClock:
    """A `ClockPort` fake. Starts at a fixed instant; advance manually via
    `tick`/`set`. Both advance methods are fake-only -- `ClockPort` itself
    exposes only `now()`."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def tick(self, delta: timedelta) -> None:
        """Advance the frozen time by `delta`."""
        self._now += delta

    def set(self, at: datetime) -> None:
        """Jump the frozen time directly to `at`."""
        self._now = at
