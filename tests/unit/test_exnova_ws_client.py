"""Unit tests for `adapters/exnova/ws_client.py` -- the thin, mockable
WebSocket wrapper. No real network I/O: a `FakeTransport` satisfying the
`WsTransport` duck type is injected via `transport_factory` in every test.
"""
from __future__ import annotations

import json
from typing import Any, List, Mapping, Optional

import pytest

from botafuturo.adapters.exnova.ws_client import (
    AuthenticationError,
    ExnovaWsClient,
    WsConnectionLost,
)

_SSID = "abc123ssid"


class FakeTransport:
    """Records every sent frame; replays a preloaded queue of incoming
    messages (dicts) on `recv()`, JSON-encoding them like a real socket
    would. `recv()` raises `TimeoutError` once the queue is exhausted,
    matching `websockets.sync.client`'s real timeout behavior."""

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


def _authenticated_msg() -> Mapping[str, Any]:
    return {
        "name": "authenticated",
        "msg": True,
        "client_session_id": "uuid-1",
        "request_id": "",
    }


def test_connect_sends_authenticate_message_first() -> None:
    transport = FakeTransport(incoming=[_authenticated_msg()])
    client = ExnovaWsClient(transport_factory=lambda url: transport)

    client.connect(_SSID)

    assert transport.sent[0] == {
        "name": "authenticate",
        "msg": {"ssid": _SSID, "protocol": 3, "client_session_id": ""},
    }


def test_connect_succeeds_when_server_confirms_authenticated() -> None:
    transport = FakeTransport(incoming=[_authenticated_msg()])
    client = ExnovaWsClient(transport_factory=lambda url: transport)

    client.connect(_SSID)  # must not raise


def test_connect_raises_authentication_error_when_server_rejects() -> None:
    transport = FakeTransport(incoming=[{"name": "authenticated", "msg": False}])
    client = ExnovaWsClient(transport_factory=lambda url: transport)

    with pytest.raises(AuthenticationError):
        client.connect(_SSID)


def test_connect_raises_authentication_error_on_unexpected_first_message() -> None:
    transport = FakeTransport(incoming=[{"name": "front", "msg": "host"}])
    client = ExnovaWsClient(transport_factory=lambda url: transport)

    with pytest.raises(AuthenticationError):
        client.connect(_SSID)


def test_disconnect_closes_the_transport() -> None:
    transport = FakeTransport(incoming=[_authenticated_msg()])
    client = ExnovaWsClient(transport_factory=lambda url: transport)
    client.connect(_SSID)

    client.disconnect()

    assert transport.closed is True


def test_disconnect_is_idempotent_when_never_connected() -> None:
    client = ExnovaWsClient(transport_factory=lambda url: FakeTransport())

    client.disconnect()  # must not raise


def test_subscribe_sends_a_subscribe_message_frame() -> None:
    transport = FakeTransport(incoming=[_authenticated_msg()])
    client = ExnovaWsClient(transport_factory=lambda url: transport)
    client.connect(_SSID)

    client.subscribe("candle-generated", "req-1", params={"active_id": 86, "size": 1})

    assert transport.sent[-1] == {
        "name": "subscribeMessage",
        "request_id": "req-1",
        "msg": {"version": "1.0", "name": "candle-generated", "params": {"active_id": 86, "size": 1}},
    }


def test_unsubscribe_sends_an_unsubscribe_message_frame() -> None:
    transport = FakeTransport(incoming=[_authenticated_msg()])
    client = ExnovaWsClient(transport_factory=lambda url: transport)
    client.connect(_SSID)

    client.unsubscribe("candle-generated", "req-1", params={"active_id": 86})

    assert transport.sent[-1] == {
        "name": "unsubscribeMessage",
        "request_id": "req-1",
        "msg": {"version": "1.0", "name": "candle-generated", "params": {"active_id": 86}},
    }


def test_receive_returns_the_next_parsed_message() -> None:
    push = {"name": "timeSync", "msg": 1780000000500}
    transport = FakeTransport(incoming=[_authenticated_msg(), push])
    client = ExnovaWsClient(transport_factory=lambda url: transport)
    client.connect(_SSID)

    message = client.receive()

    assert message == push


def test_receive_raises_ws_connection_lost_on_timeout() -> None:
    transport = FakeTransport(incoming=[_authenticated_msg()])
    client = ExnovaWsClient(transport_factory=lambda url: transport)
    client.connect(_SSID)  # consumes the only queued message

    with pytest.raises(WsConnectionLost):
        client.receive()


def test_receive_raises_ws_connection_lost_on_invalid_json() -> None:
    class BadJsonTransport(FakeTransport):
        def recv(self, timeout: Optional[float] = None) -> str:
            if self.sent and len(self.sent) == 1:
                # First recv (during the connect() handshake) still returns
                # a valid `authenticated` confirmation; only the SECOND
                # recv (the one under test) returns malformed JSON.
                return super().recv(timeout=timeout)
            return "not-json{"

    transport = BadJsonTransport(incoming=[_authenticated_msg()])
    client = ExnovaWsClient(transport_factory=lambda url: transport)
    client.connect(_SSID)

    with pytest.raises(WsConnectionLost):
        client.receive()
