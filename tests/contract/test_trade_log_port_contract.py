"""Conformance tests for `TradeLogPort` implementations.

Parametrized over every known implementation of `TradeLogPort`:
`InMemoryTradeLog` (the test fake) and `JsonlTradeLog` (the production
JSON-Lines journal adapter, a later PR joins the same list once it exists).
Each factory takes `tmp_path` so `JsonlTradeLog` gets a fresh, isolated file
per test invocation without polluting the real filesystem.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from botafuturo.adapters.logging.journal import JsonlTradeLog
from botafuturo.adapters.logging.redaction import SecretRegistry
from botafuturo.ports.trade_log import TradeLogPort
from tests.fakes.trade_log import InMemoryTradeLog


def _make_in_memory_trade_log(tmp_path: Path) -> InMemoryTradeLog:
    return InMemoryTradeLog()


def _make_jsonl_trade_log(tmp_path: Path) -> JsonlTradeLog:
    return JsonlTradeLog(tmp_path / "trades.jsonl", SecretRegistry())


TRADE_LOG_FACTORIES = [
    pytest.param(_make_in_memory_trade_log, id="InMemoryTradeLog"),
    pytest.param(_make_jsonl_trade_log, id="JsonlTradeLog"),
]


@pytest.mark.contract
class TestTradeLogPortContract:
    @pytest.mark.parametrize("make", TRADE_LOG_FACTORIES)
    def test_conforms_to_protocol_shape(self, make, tmp_path) -> None:
        trade_log = make(tmp_path)
        assert isinstance(trade_log, TradeLogPort)

    @pytest.mark.parametrize("make", TRADE_LOG_FACTORIES)
    def test_exposes_no_update_or_delete_method(self, make, tmp_path) -> None:
        trade_log = make(tmp_path)
        assert not hasattr(trade_log, "update")
        assert not hasattr(trade_log, "delete")
        assert not hasattr(trade_log, "remove")

    @pytest.mark.parametrize("make", TRADE_LOG_FACTORIES)
    def test_read_returns_all_appended_records_without_filters(self, make, tmp_path) -> None:
        trade_log = make(tmp_path)
        trade_log.append({"order_id": "a", "ts": date(2026, 1, 1)})
        trade_log.append({"order_id": "b", "ts": date(2026, 1, 2)})

        records = list(trade_log.read())

        assert [r["order_id"] for r in records] == ["a", "b"]

    @pytest.mark.parametrize("make", TRADE_LOG_FACTORIES)
    def test_read_filters_by_since_and_until(self, make, tmp_path) -> None:
        trade_log = make(tmp_path)
        trade_log.append({"order_id": "a", "ts": date(2026, 1, 1)})
        trade_log.append({"order_id": "b", "ts": date(2026, 1, 5)})
        trade_log.append({"order_id": "c", "ts": date(2026, 1, 10)})

        records = list(trade_log.read(since=date(2026, 1, 2), until=date(2026, 1, 9)))

        assert [r["order_id"] for r in records] == ["b"]
