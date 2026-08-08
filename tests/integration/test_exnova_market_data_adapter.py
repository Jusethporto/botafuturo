"""Integration tests for `ExnovaMarketDataAdapter` driven against a FAKE
WebSocket transport and a fake HTTP login -- NEVER a real network
connection. Fixture messages under `tests/fixtures/exnova/` are transcribed
from the documented example payloads in `docs/spike-report.md`.

Hard requirement (per the design's testing strategy): zero real network
calls. Every WS/HTTP interaction below goes through an injected fake
(`transport_factory`, `http_post`) -- nothing here reaches
`trade.exnova.com` or any other real host.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Mapping, Optional

import pytest
from pydantic import SecretStr

from botafuturo.adapters.exnova.market_data import ExnovaMarketDataAdapter
from botafuturo.adapters.logging.redaction import SecretRegistry
from botafuturo.domain.models import Candle
from botafuturo.ports.market_data import GapMarker, MarketDataPort

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "exnova"
_EMAIL = SecretStr("trader@example.com")
_PASSWORD = SecretStr("s3cr3t-password")
_SSID = "fake-ssid-value"
_ASSET = "EURUSD-OTC"
_ACTIVE_ID = 86
_TIMEFRAME_S = 1


def _load_json(name: str) -> Mapping[str, Any]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _load_candle_pushes() -> List[Mapping[str, Any]]:
    lines = (_FIXTURES / "candle_generated.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


class FakeTransport:
    def __init__(self, incoming: Optional[List[Mapping[str, Any]]] = None) -> None:
        self.sent: List[Mapping[str, Any]] = []
        self._incoming = list(incoming or [])
        self.closed = False

    def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    def recv(self, timeout: Optional[float] = None) -> str:
        if not self._incoming:
            raise TimeoutError("no message received within timeout")
        return json.dumps(self._incoming.pop(0))

    def close(self) -> None:
        self.closed = True


@dataclass
class _FakeHttpResponse:
    status_code: int
    _body: Mapping[str, Any]

    def json(self) -> Mapping[str, Any]:
        return self._body


def _fake_http_post(url: str, *, json: Mapping[str, Any]) -> _FakeHttpResponse:
    return _FakeHttpResponse(
        status_code=200,
        _body={"code": "success", "ssid": _SSID, "user_id": 1, "company_id": 15},
    )


def _make_adapter(transports: List[FakeTransport], **overrides) -> ExnovaMarketDataAdapter:
    factory_calls = {"n": 0}

    def transport_factory(url: str) -> FakeTransport:
        transport = transports[factory_calls["n"]]
        factory_calls["n"] += 1
        return transport

    kwargs = dict(
        email=_EMAIL,
        password=_PASSWORD,
        asset=_ASSET,
        active_id=_ACTIVE_ID,
        transport_factory=transport_factory,
        http_post=_fake_http_post,
        idle_timeout_s=0.01,
        rng=random.Random(1234),
        sleep=lambda seconds: None,  # never actually sleep in tests
    )
    kwargs.update(overrides)
    return ExnovaMarketDataAdapter(**kwargs)


def test_adapter_structurally_conforms_to_market_data_port() -> None:
    """Structural (Protocol-shape) conformance -- kept HERE rather than in
    `tests/contract/test_market_data_port_contract.py`'s shared
    `MARKET_DATA_FACTORIES` list, since that suite also asserts real
    `history`/`price_at` behavior this adapter intentionally does not
    implement in v1 (see that file's module docstring)."""
    adapter = _make_adapter([FakeTransport()])

    assert isinstance(adapter, MarketDataPort)


def test_connect_performs_http_login_then_ws_authenticate() -> None:
    transport = FakeTransport(incoming=[_load_json("authenticated.json")])
    adapter = _make_adapter([transport])

    adapter.connect()

    assert transport.sent[0]["name"] == "authenticate"
    assert transport.sent[0]["msg"]["ssid"] == _SSID


def test_connect_registers_ssid_into_provided_secret_registry() -> None:
    registry = SecretRegistry()
    transport = FakeTransport(incoming=[_load_json("authenticated.json")])
    adapter = _make_adapter([transport], registry=registry)

    adapter.connect()

    assert _SSID in registry.values


def test_disconnect_closes_the_underlying_transport() -> None:
    transport = FakeTransport(incoming=[_load_json("authenticated.json")])
    adapter = _make_adapter([transport])
    adapter.connect()

    adapter.disconnect()

    assert transport.closed is True


def test_history_raises_not_implemented() -> None:
    adapter = _make_adapter([FakeTransport()])

    with pytest.raises(NotImplementedError):
        adapter.history(_ASSET, _TIMEFRAME_S, count=10)


def test_price_at_raises_not_implemented() -> None:
    from datetime import datetime, timezone

    adapter = _make_adapter([FakeTransport()])

    with pytest.raises(NotImplementedError):
        adapter.price_at(_ASSET, datetime.now(timezone.utc))


def test_stream_closed_candles_yields_mapped_candles_in_order() -> None:
    pushes = _load_candle_pushes()
    incoming = [
        _load_json("authenticated.json"),
        _load_json("front.json"),
        _load_json("time_sync.json"),
        pushes[0],
        pushes[1],
        pushes[2],
    ]
    transport = FakeTransport(incoming=incoming)
    adapter = _make_adapter([transport])

    stream = adapter.stream_closed_candles(_ASSET, _TIMEFRAME_S)
    candles = [next(stream) for _ in range(3)]

    assert all(isinstance(c, Candle) for c in candles)
    assert [c.asset for c in candles] == [_ASSET] * 3
    assert [str(c.close) for c in candles] == ["0.98442", "0.98445", "0.98441"]


def test_stream_closed_candles_subscribes_for_the_configured_active_id() -> None:
    pushes = _load_candle_pushes()
    incoming = [_load_json("authenticated.json"), pushes[0]]
    transport = FakeTransport(incoming=incoming)
    adapter = _make_adapter([transport])

    stream = adapter.stream_closed_candles(_ASSET, _TIMEFRAME_S)
    next(stream)

    subscribe_frames = [f for f in transport.sent if f["name"] == "subscribeMessage"]
    assert len(subscribe_frames) == 1
    assert subscribe_frames[0]["msg"]["name"] == "candle-generated"
    assert subscribe_frames[0]["msg"]["params"]["active_id"] == _ACTIVE_ID


def test_stream_closed_candles_rejects_an_asset_it_was_not_configured_for() -> None:
    adapter = _make_adapter([FakeTransport(incoming=[_load_json("authenticated.json")])])

    with pytest.raises(ValueError):
        list(adapter.stream_closed_candles("GBPUSD-OTC", _TIMEFRAME_S))


def test_a_simulated_connection_drop_yields_a_gap_marker_and_reconnects() -> None:
    pushes = _load_candle_pushes()
    # First transport: authenticate, then ONE candle, then the queue runs
    # dry -> `recv()` raises TimeoutError, simulating a dead connection
    # (the timeSync-absence signal).
    transport_1 = FakeTransport(incoming=[_load_json("authenticated.json"), pushes[0]])
    # Second transport: the adapter reconnects onto this one (fresh login +
    # WS auth), then more candles arrive normally.
    transport_2 = FakeTransport(incoming=[_load_json("authenticated.json"), pushes[1]])

    adapter = _make_adapter([transport_1, transport_2])
    stream = adapter.stream_closed_candles(_ASSET, _TIMEFRAME_S)

    first = next(stream)
    assert isinstance(first, Candle)
    assert str(first.close) == "0.98442"

    second = next(stream)  # transport_1 is now exhausted -> reconnect
    assert isinstance(second, GapMarker)
    assert second.asset == _ASSET
    assert second.timeframe_s == _TIMEFRAME_S

    third = next(stream)  # resumed on transport_2
    assert isinstance(third, Candle)
    assert str(third.close) == "0.98445"

    # Reconnect actually happened: transport_1 was closed and transport_2
    # received its own authenticate + re-subscribe frames.
    assert transport_1.closed is True
    assert transport_2.sent[0]["name"] == "authenticate"
    subscribe_frames = [f for f in transport_2.sent if f["name"] == "subscribeMessage"]
    assert len(subscribe_frames) == 1


# NOTE on the "no live network" hard requirement: every test above
# constructs `ExnovaMarketDataAdapter` with an explicit `transport_factory`
# (a `FakeTransport`) and `http_post` (`_fake_http_post`) override -- the
# real `default_transport_factory` (which imports `websockets.sync.client`)
# and the real `_default_http_post` (which imports `httpx`) are never
# reached by this module. A self-referential source-text scan was
# considered and rejected here: it is trivially self-defeating (the
# assertion string itself contains the substring it checks for) and adds
# no real signal beyond what the fixtures/fakes above already guarantee by
# construction.
