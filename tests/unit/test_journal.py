"""Unit tests for `JsonlTradeLog`: JSON-Lines file-backed `TradeLogPort`
implementation.

Complements `tests/contract/test_trade_log_port_contract.py` (which proves
port conformance) with adapter-specific persistence and no-leakage proofs.
"""
from __future__ import annotations

from datetime import date

from botafuturo.adapters.logging.journal import JsonlTradeLog
from botafuturo.adapters.logging.redaction import SecretRegistry

_SECRET = "s3kr1t-account-password"


def test_append_then_read_round_trips_record(tmp_path) -> None:
    trade_log = JsonlTradeLog(tmp_path / "trades.jsonl", SecretRegistry())
    trade_log.append({"order_id": "a", "ts": date(2026, 1, 1)})

    records = list(trade_log.read())

    assert records[0]["order_id"] == "a"


def test_append_redacts_registered_secret_before_writing_to_disk(tmp_path) -> None:
    registry = SecretRegistry()
    registry.register(_SECRET)
    path = tmp_path / "trades.jsonl"
    trade_log = JsonlTradeLog(path, registry)

    trade_log.append({"order_id": "a", "ts": date(2026, 1, 1), "note": _SECRET})

    raw_bytes = path.read_bytes()
    assert _SECRET.encode("utf-8") not in raw_bytes
    assert b"***REDACTED***" in raw_bytes


def test_read_skips_malformed_line_without_crashing(tmp_path) -> None:
    path = tmp_path / "trades.jsonl"
    trade_log = JsonlTradeLog(path, SecretRegistry())
    trade_log.append({"order_id": "a", "ts": date(2026, 1, 1)})
    with path.open("a", encoding="utf-8") as fh:
        fh.write("not valid json\n")
    trade_log.append({"order_id": "b", "ts": date(2026, 1, 2)})

    records = list(trade_log.read())

    assert [r["order_id"] for r in records] == ["a", "b"]


def test_read_from_nonexistent_file_yields_no_records(tmp_path) -> None:
    trade_log = JsonlTradeLog(tmp_path / "missing.jsonl", SecretRegistry())

    records = list(trade_log.read())

    assert records == []


def test_read_filters_by_since_and_until(tmp_path) -> None:
    trade_log = JsonlTradeLog(tmp_path / "trades.jsonl", SecretRegistry())
    trade_log.append({"order_id": "a", "ts": date(2026, 1, 1)})
    trade_log.append({"order_id": "b", "ts": date(2026, 1, 5)})
    trade_log.append({"order_id": "c", "ts": date(2026, 1, 10)})

    records = list(trade_log.read(since=date(2026, 1, 2), until=date(2026, 1, 9)))

    assert [r["order_id"] for r in records] == ["b"]
