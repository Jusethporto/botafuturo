"""`ClockPort`: abstraction over wall-clock time.

Injecting time through a port (rather than calling `datetime.now()` directly
from domain or adapter code) keeps time-dependent logic deterministic and
testable -- see `tests/fakes/clock.py::FrozenClock`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class ClockPort(Protocol):
    """Read-only source of the current time."""

    def now(self) -> datetime:
        """Return the current time (timezone-aware)."""
        ...
