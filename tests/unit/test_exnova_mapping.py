"""Unit tests for `adapters/exnova/mapping.py` -- pure functions mapping raw
Exnova WS message dicts to domain objects.

Fixtures under `tests/fixtures/exnova/` are transcribed from the DOCUMENTED
example payloads in `docs/spike-report.md` (safe: real observed structural
shapes, no real secrets) -- never from raw live capture data.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from botafuturo.adapters.exnova.mapping import MappingError, to_candle
from botafuturo.domain.models import Candle

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "exnova"
_ASSET = "EURUSD-OTC"


def _load_candle_pushes() -> list:
    lines = (_FIXTURES / "candle_generated.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_to_candle_maps_documented_example_payload() -> None:
    raw = _load_candle_pushes()[0]

    candle = to_candle(raw, _ASSET)

    assert isinstance(candle, Candle)
    assert candle.asset == _ASSET
    assert candle.open == Decimal("0.9844")
    assert candle.close == Decimal("0.98442")
    assert candle.low == Decimal("0.98439")
    assert candle.high == Decimal("0.98443")
    assert candle.volume == Decimal("12")
    assert candle.timeframe_s == 1


def test_to_candle_derives_open_time_from_the_from_field() -> None:
    raw = _load_candle_pushes()[0]

    candle = to_candle(raw, _ASSET)

    assert candle.open_time.timestamp() == 1780000000


def test_to_candle_echoes_the_caller_supplied_asset_not_active_id() -> None:
    raw = _load_candle_pushes()[0]

    candle = to_candle(raw, "GBPUSD-OTC")

    assert candle.asset == "GBPUSD-OTC"


def test_to_candle_maps_every_fixture_message_without_error() -> None:
    for raw in _load_candle_pushes():
        candle = to_candle(raw, _ASSET)
        assert isinstance(candle, Candle)


def test_to_candle_rejects_a_non_candle_generated_message() -> None:
    raw = json.loads((_FIXTURES / "time_sync.json").read_text(encoding="utf-8"))

    with pytest.raises(MappingError):
        to_candle(raw, _ASSET)


def test_to_candle_rejects_a_malformed_push_missing_msg_body() -> None:
    raw = {"name": "candle-generated"}

    with pytest.raises(MappingError):
        to_candle(raw, _ASSET)


def test_to_candle_rejects_a_push_missing_a_required_field() -> None:
    raw = {
        "name": "candle-generated",
        "msg": {"active_id": 86, "size": 1, "from": 1780000000, "open": 0.1},
        # missing close/min/max/volume
    }

    with pytest.raises(MappingError):
        to_candle(raw, _ASSET)
