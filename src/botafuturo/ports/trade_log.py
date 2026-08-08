"""`TradeLogPort`: append-only audit trail of settled trades.

Deliberately has NO update or delete method. This is a design-level
guarantee, not an accident: a trade log is a compliance/audit artifact, and
once a record is appended it must never be silently mutated or removed by
application code. Corrections (if ever needed) belong to a separate,
explicit, out-of-band process -- never through this port.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterator, Mapping, Optional, Protocol, runtime_checkable


@runtime_checkable
class TradeLogPort(Protocol):
    """Append-only trade record sink and reader."""

    def append(self, record: Mapping[str, Any]) -> None:
        """Append `record` to the log. Never overwrites or mutates existing records."""
        ...

    def read(
        self, since: Optional[date] = None, until: Optional[date] = None
    ) -> Iterator[Mapping[str, Any]]:
        """Yield appended records, optionally filtered to `[since, until]` (inclusive)."""
        ...
