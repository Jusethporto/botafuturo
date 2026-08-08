"""Conformance tests for `TradeLogPort` implementations.

Parametrized over every known implementation of `TradeLogPort`. Today that
is only `InMemoryTradeLog`; a file/db-backed adapter (a later PR) joins
this same list once it exists.
"""
from __future__ import annotations

from datetime import date

import pytest

from botafuturo.ports.trade_log import TradeLogPort
from tests.fakes.trade_log import InMemoryTradeLog

TRADE_LOG_FACTORIES = [pytest.param(InMemoryTradeLog, id="InMemoryTradeLog")]


@pytest.mark.contract
class TestTradeLogPortContract:
    @pytest.mark.parametrize("make", TRADE_LOG_FACTORIES)
    def test_conforms_to_protocol_shape(self, make) -> None:
        trade_log = make()
        assert isinstance(trade_log, TradeLogPort)

    @pytest.mark.parametrize("make", TRADE_LOG_FACTORIES)
    def test_exposes_no_update_or_delete_method(self, make) -> None:
        trade_log = make()
        assert not hasattr(trade_log, "update")
        assert not hasattr(trade_log, "delete")
        assert not hasattr(trade_log, "remove")

    @pytest.mark.parametrize("make", TRADE_LOG_FACTORIES)
    def test_read_returns_all_appended_records_without_filters(self, make) -> None:
        trade_log = make()
        trade_log.append({"order_id": "a", "ts": date(2026, 1, 1)})
        trade_log.append({"order_id": "b", "ts": date(2026, 1, 2)})

        records = list(trade_log.read())

        assert [r["order_id"] for r in records] == ["a", "b"]

    @pytest.mark.parametrize("make", TRADE_LOG_FACTORIES)
    def test_read_filters_by_since_and_until(self, make) -> None:
        trade_log = make()
        trade_log.append({"order_id": "a", "ts": date(2026, 1, 1)})
        trade_log.append({"order_id": "b", "ts": date(2026, 1, 5)})
        trade_log.append({"order_id": "c", "ts": date(2026, 1, 10)})

        records = list(trade_log.read(since=date(2026, 1, 2), until=date(2026, 1, 9)))

        assert [r["order_id"] for r in records] == ["b"]
