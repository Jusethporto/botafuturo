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


def _candle_push(
    *, from_ts: int, size: int = _TIMEFRAME_S, close: float, active_id: int = _ACTIVE_ID
) -> Mapping[str, Any]:
    """Build one synthetic `candle-generated` push for a given window
    (`from_ts`/`size`) and `close` value -- mirrors the REAL server
    behavior confirmed against a live run: the server pushes roughly once
    per second regardless of `size`, repeating the SAME `from`/`to` window
    (with `close`/`min`/`max` evolving) until that window's real duration
    elapses, then starts a new window. Tests build sequences of these to
    simulate multiple live-update pushes for the same still-forming bar
    followed by a rollover to the next one (see
    `test_exnova_market_data_adapter.py`'s module docstring and
    `docs/spike-report.md`)."""
    return {
        "name": "candle-generated",
        "microserviceName": "quotes",
        "msg": {
            "active_id": active_id,
            "size": size,
            "at": from_ts * 1_000_000_000,
            "from": from_ts,
            "to": from_ts + size,
            "id": from_ts,
            "open": close,
            "close": close,
            "min": close,
            "max": close,
            "ask": close,
            "bid": close,
            "volume": 1,
            "phase": "T",
        },
    }


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
    # `candle_generated.jsonl`'s 3 fixture pushes each carry a DIFFERENT
    # `from` (T0, T0+1, T0+2 -- genuinely separate closed 1-second windows,
    # since `size:1` is the one case where push-cadence-happens-to-equal-
    # bar-duration per docs/spike-report.md). Feeding all 3 therefore rolls
    # over TWICE: the 1st push opens+buffers window T0 (no yield yet), the
    # 2nd push's *different* `from` closes T0 (yielded) and opens T1, and
    # the 3rd push's *different* `from` closes T1 (yielded) and opens T2 --
    # T2 itself stays buffered (never yielded) since no 4th push closes it.
    # So 3 pushes correctly yield only 2 candles, not 3 -- see this
    # module's regression test below for the general (same-window, evolving
    # `close`) case that most directly demonstrates the bugfix.
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
    candles = [next(stream) for _ in range(2)]

    assert all(isinstance(c, Candle) for c in candles)
    assert [c.asset for c in candles] == [_ASSET] * 2
    assert [str(c.close) for c in candles] == ["0.98442", "0.98445"]


def test_stream_closed_candles_only_yields_a_candle_once_its_window_rolls_over() -> None:
    """Core regression test for the premature-warm-up bug: the real Exnova
    server pushes ~once/second for the STILL-FORMING bar of the subscribed
    `size`, repeating the same `from`/`to` window with an evolving `close`
    until it genuinely closes (see docs/spike-report.md and this module's
    docstring). `stream_closed_candles()` must only yield once a window
    rollover (a NEW `from`) is observed, and must yield the FINAL buffered
    state of the window that just closed -- not every intermediate push."""
    t0, t1, t2 = 1780000000, 1780000060, 1780000120
    pushes = [
        _candle_push(from_ts=t0, size=60, close=0.98440),
        _candle_push(from_ts=t0, size=60, close=0.98443),
        _candle_push(from_ts=t0, size=60, close=0.98444),  # final T0 state
        _candle_push(from_ts=t1, size=60, close=0.98446),
        _candle_push(from_ts=t1, size=60, close=0.98448),  # final T1 state
        _candle_push(from_ts=t2, size=60, close=0.98450),  # T2 never closes here
    ]
    incoming = [_load_json("authenticated.json"), *pushes]
    transport = FakeTransport(incoming=incoming)
    adapter = _make_adapter([transport])

    stream = adapter.stream_closed_candles(_ASSET, 60)
    first = next(stream)
    second = next(stream)

    assert isinstance(first, Candle)
    assert isinstance(second, Candle)
    assert str(first.close) == "0.98444"
    assert first.open_time.timestamp() == t0
    assert str(second.close) == "0.98448"
    assert second.open_time.timestamp() == t1
    # Exactly 2 candles yielded from 6 pushes -- NOT 6. The T2 push is
    # still buffered (its window never rolled over in this test), so the
    # next event out of the generator is the queue-exhaustion GapMarker,
    # never a T2 candle -- the still-forming T2 candle is correctly never
    # yielded (see this module's docstring on graceful exhaustion).
    third = next(stream)
    assert isinstance(third, GapMarker)


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
    # `active_id`/`size` MUST be nested inside a `routingFilters` object
    # inside `params` (confirmed via a real browser capture, see
    # docs/spike-report.md's "CRITICAL — corrected 2026-08-08" entry) --
    # flat `params: {active_id, size}` is silently ignored by the server
    # (no error, just zero matching `candle-generated` pushes).
    routing_filters = subscribe_frames[0]["msg"]["params"]["routingFilters"]
    assert routing_filters["active_id"] == _ACTIVE_ID
    assert routing_filters["size"] == _TIMEFRAME_S


def test_stream_closed_candles_rejects_an_asset_it_was_not_configured_for() -> None:
    adapter = _make_adapter([FakeTransport(incoming=[_load_json("authenticated.json")])])

    with pytest.raises(ValueError):
        list(adapter.stream_closed_candles("GBPUSD-OTC", _TIMEFRAME_S))


def test_a_simulated_connection_drop_yields_a_gap_marker_and_reconnects() -> None:
    t0, t5, t6 = 1780000000, 1780000300, 1780000360
    # First transport: authenticate, then ONE still-forming candle push for
    # window T0 (no rollover ever observed for it) -- then the queue runs
    # dry -> `recv()` raises TimeoutError, simulating a dead connection
    # (the timeSync-absence signal). Because T0 never rolled over, it must
    # stay buffered-and-discarded, NEVER yielded.
    transport_1 = FakeTransport(
        incoming=[_load_json("authenticated.json"), _candle_push(from_ts=t0, close=0.98440)]
    )
    # Second transport: the adapter reconnects onto this one (fresh login +
    # WS auth). A fresh T5 push arrives, then a T6 push rolls the window
    # over, closing T5 -- proving the resumed stream tracks ITS OWN windows
    # from scratch, never leaking the stale pre-reconnect T0 buffer.
    transport_2 = FakeTransport(
        incoming=[
            _load_json("authenticated.json"),
            _candle_push(from_ts=t5, close=0.98446),
            _candle_push(from_ts=t6, close=0.98450),
        ]
    )

    adapter = _make_adapter([transport_1, transport_2])
    stream = adapter.stream_closed_candles(_ASSET, _TIMEFRAME_S)

    first = next(stream)  # transport_1's lone T0 push never closes -> reconnect
    assert isinstance(first, GapMarker)
    assert first.asset == _ASSET
    assert first.timeframe_s == _TIMEFRAME_S

    second = next(stream)  # resumed on transport_2, T5 closes once T6 arrives
    assert isinstance(second, Candle)
    assert str(second.close) == "0.98446"
    assert second.open_time.timestamp() == t5

    # Reconnect actually happened: transport_1 was closed and transport_2
    # received its own authenticate + re-subscribe frames.
    assert transport_1.closed is True
    assert transport_2.sent[0]["name"] == "authenticate"
    subscribe_frames = [f for f in transport_2.sent if f["name"] == "subscribeMessage"]
    assert len(subscribe_frames) == 1


def test_reconnect_discards_the_stale_pre_disconnect_buffered_candle() -> None:
    """The in-progress-candle buffer must NOT survive a reconnect: the
    resumed stream may have missed the actual close of whatever was
    buffered, so it must never be yielded, merged with, or otherwise
    influence post-reconnect candles."""
    t0, t5, t6 = 1780000000, 1780000300, 1780000360
    transport_1 = FakeTransport(
        incoming=[_load_json("authenticated.json"), _candle_push(from_ts=t0, close=0.98440)]
    )
    transport_2 = FakeTransport(
        incoming=[
            _load_json("authenticated.json"),
            _candle_push(from_ts=t5, close=0.98446),
            _candle_push(from_ts=t6, close=0.98450),
        ]
    )
    adapter = _make_adapter([transport_1, transport_2])
    stream = adapter.stream_closed_candles(_ASSET, _TIMEFRAME_S)

    seen = [next(stream), next(stream)]

    candles_seen = [event for event in seen if isinstance(event, Candle)]
    assert len(candles_seen) == 1
    only_candle = candles_seen[0]
    # Only the T5-window candle ever appears -- the stale pre-reconnect T0
    # buffer (close=0.98440) is never yielded at any point.
    assert str(only_candle.close) == "0.98446"
    assert only_candle.open_time.timestamp() == t5
    assert all(str(c.close) != "0.98440" for c in candles_seen)


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
