"""`InMemoryTradeLog`: a `TradeLogPort` fake backed by a list.

Append-only: this fake exposes no method to mutate or remove a record after
it has been appended (matching the `TradeLogPort` contract). `read`
filtering assumes each record carries a `"ts"` or `"timestamp"` field whose
value is a `date`/`datetime`.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterator, List, Mapping, Optional


class InMemoryTradeLog:
    """List-backed `TradeLogPort` fake. `append` is the only write operation."""

    def __init__(self) -> None:
        self._records: List[Mapping[str, Any]] = []

    def append(self, record: Mapping[str, Any]) -> None:
        self._records.append(dict(record))

    def read(
        self, since: Optional[date] = None, until: Optional[date] = None
    ) -> Iterator[Mapping[str, Any]]:
        for record in self._records:
            record_date = _record_date(record)
            if since is not None and record_date < since:
                continue
            if until is not None and record_date > until:
                continue
            yield record


def _record_date(record: Mapping[str, Any]) -> date:
    ts = record.get("ts", record.get("timestamp"))
    if isinstance(ts, datetime):
        return ts.date()
    if isinstance(ts, date):
        return ts
    raise ValueError(
        "record must contain a 'ts' or 'timestamp' date/datetime field for filtering"
    )
