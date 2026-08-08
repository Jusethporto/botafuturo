"""`JsonlTradeLog`: JSON-Lines file-backed `TradeLogPort` implementation.

Every appended record is redacted (via `redact_mapping`) BEFORE
serialization, so secrets never touch disk -- the redaction chokepoint is
applied at the point of persistence, not left to callers to remember at
every call site. Directory/date-rollover naming (e.g. `journal/{date}.jsonl`)
is left to the CLI layer in a later PR; this adapter takes a direct file
path, matching `TradeLogPort`'s append-only, no-update/no-delete contract.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional, Union

from botafuturo.adapters.logging.redaction import SecretRegistry, redact_mapping


class JsonlTradeLog:
    """Append-only `TradeLogPort` implementation backed by a `.jsonl` file."""

    def __init__(self, path: Union[str, Path], registry: SecretRegistry) -> None:
        self._path = Path(path)
        self._registry = registry

    def append(self, record: Mapping[str, Any]) -> None:
        redacted = redact_mapping(record, self._registry)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(redacted, default=str))
            fh.write("\n")
            fh.flush()

    def read(
        self, since: Optional[date] = None, until: Optional[date] = None
    ) -> Iterator[Mapping[str, Any]]:
        if not self._path.exists():
            return

        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                record_date = _record_date(record)
                if record_date is not None:
                    if since is not None and record_date < since:
                        continue
                    if until is not None and record_date > until:
                        continue
                yield record


def _record_date(record: Mapping[str, Any]) -> Optional[date]:
    ts = record.get("ts", record.get("timestamp"))
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts).date()
    except ValueError:
        return None
