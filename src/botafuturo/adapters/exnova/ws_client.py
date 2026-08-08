"""Thin, mockable wrapper around a WebSocket connection to Exnova.

`ExnovaWsClient` owns the connection lifecycle (connect + `authenticate`
handshake, send, receive, close). It depends only on a small duck-typed
`WsTransport` shape (`send`/`recv`/`close`) obtained from an injectable
`transport_factory` -- never the real `websockets` library directly -- so
`market_data.py` (and this module's own tests) never need a real network
connection. The default factory (`default_transport_factory`) is the one
and only place `websockets` is actually imported, and only lazily, at call
time.

Message envelope (see `docs/spike-report.md`):

    # client -> server
    {"name": "sendMessage", "request_id": "<id>",
     "msg": {"name": "<command>", "version": "<ver>", "body": {...}}}
    {"name": "subscribeMessage", "request_id": "<id>",
     "msg": {"version": "1.0", "name": "<event-name>", "params": {...}}}
    {"name": "unsubscribeMessage", ...}  # symmetric to subscribeMessage

    # server -> client
    {"request_id": "<id>", "name": "<response-type>", "msg": {...}, "status": 2000}
    {"name": "<event-name>", "microserviceName": "<service>", "msg": {...}}
"""
from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Optional, Protocol

DEFAULT_WS_URL = "wss://ws.trade.exnova.com/echo/websocket"

_AUTHENTICATE = "authenticate"
_AUTHENTICATED = "authenticated"
_SUBSCRIBE = "subscribeMessage"
_UNSUBSCRIBE = "unsubscribeMessage"

#: Default protocol version sent in the `authenticate` handshake (observed
#: value, see docs/spike-report.md).
_AUTH_PROTOCOL_VERSION = 3
#: Default subscription envelope version (observed value).
_SUBSCRIPTION_VERSION = "1.0"
#: Bounded number of non-matching messages `connect()` will skip while
#: waiting for the `authenticated` confirmation (see `connect()` docstring).
_MAX_AUTH_SKIP = 20


class WsTransport(Protocol):
    """Minimal duck-typed shape `ExnovaWsClient` needs from a WebSocket
    connection -- enough of `websockets.sync.client.ClientConnection`'s
    surface to send/receive JSON text frames and close cleanly, and
    nothing else. Any fake/mock satisfying this shape works as a drop-in
    replacement in tests."""

    def send(self, message: str) -> None: ...

    def recv(self, timeout: Optional[float] = None) -> str: ...

    def close(self) -> None: ...


TransportFactory = Callable[[str], WsTransport]


def default_transport_factory(url: str) -> WsTransport:
    """Real transport factory: opens a real, synchronous WebSocket
    connection via `websockets.sync.client.connect`. `websockets` is
    imported lazily here (not at module import time) so this module stays
    importable -- e.g. by architecture tests that import every module
    under `src/botafuturo` -- even in an environment where `websockets`
    is not (yet) installed, as long as nothing actually tries to connect.
    """
    from websockets.sync.client import connect

    return connect(url)


class AuthenticationError(Exception):
    """Raised when the WS `authenticate` handshake does not succeed."""


class WsConnectionLost(Exception):
    """Raised by `ExnovaWsClient.receive()` when the connection appears
    dead: either the transport's `recv()` timed out (no message arrived
    within the configured timeout -- the `timeSync`-absence signal
    documented in docs/spike-report.md's Heartbeat section) or the
    transport otherwise failed to produce a valid, JSON-decodable message
    (e.g. the underlying socket reports the connection as closed).
    """


class ExnovaWsClient:
    """Connects to the Exnova WS endpoint, performs the `authenticate`
    handshake, and exposes `subscribe`/`unsubscribe`/`receive` for
    higher-level callers (`market_data.py`). Does NOT itself implement any
    reconnect/backoff policy -- that is `reconnect.py` plus the calling
    adapter's responsibility; this class is a single-connection wrapper.
    """

    def __init__(
        self,
        url: str = DEFAULT_WS_URL,
        transport_factory: TransportFactory = default_transport_factory,
        *,
        recv_timeout_s: float = 5.0,
    ) -> None:
        self._url = url
        self._transport_factory = transport_factory
        self._recv_timeout_s = recv_timeout_s
        self._transport: Optional[WsTransport] = None

    def connect(self, ssid: str) -> None:
        """Open the WS connection and perform the `authenticate` handshake.

        The server does not guarantee `authenticated` is strictly the first
        message on the wire: a `timeSync` heartbeat (pushed roughly every
        second, see docs/spike-report.md's Heartbeat section) can arrive
        before the `authenticated` confirmation. This loop skips any message
        that isn't the `authenticated` confirmation, up to `_MAX_AUTH_SKIP`
        non-matching messages, to avoid mistaking a heartbeat (or any other
        stray push) for a failed handshake while still bailing out instead
        of skipping forever if `authenticated` genuinely never arrives.

        Raises:
            AuthenticationError: if the server explicitly rejects the
                handshake (`authenticated` with `msg` not `True`), or if no
                `authenticated` confirmation arrives within `_MAX_AUTH_SKIP`
                skipped messages.
        """
        self._transport = self._transport_factory(self._url)
        self._send(
            {
                "name": _AUTHENTICATE,
                "msg": {
                    "ssid": ssid,
                    "protocol": _AUTH_PROTOCOL_VERSION,
                    "client_session_id": "",
                },
            }
        )
        last_response: Mapping[str, Any] = {}
        for _ in range(_MAX_AUTH_SKIP):
            response = self._recv()
            last_response = response
            if response.get("name") == _AUTHENTICATED:
                if response.get("msg") is True:
                    return
                raise AuthenticationError(f"WS authentication failed: {response!r}")
            # Not the authenticated confirmation (e.g. a `timeSync`
            # heartbeat) -- keep reading, this is not necessarily a failure.
        raise AuthenticationError(
            "WS authentication failed: no 'authenticated' confirmation after "
            f"skipping {_MAX_AUTH_SKIP} non-matching messages; last message "
            f"seen: {last_response!r}"
        )

    def disconnect(self) -> None:
        """Close the WS connection. Idempotent: safe to call when not
        connected (or already disconnected)."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    def subscribe(
        self, event_name: str, request_id: str, *, params: Optional[Mapping[str, Any]] = None
    ) -> None:
        self._send(
            {
                "name": _SUBSCRIBE,
                "request_id": request_id,
                "msg": {
                    "version": _SUBSCRIPTION_VERSION,
                    "name": event_name,
                    "params": dict(params or {}),
                },
            }
        )

    def unsubscribe(
        self, event_name: str, request_id: str, *, params: Optional[Mapping[str, Any]] = None
    ) -> None:
        self._send(
            {
                "name": _UNSUBSCRIBE,
                "request_id": request_id,
                "msg": {
                    "version": _SUBSCRIPTION_VERSION,
                    "name": event_name,
                    "params": dict(params or {}),
                },
            }
        )

    def receive(self) -> Mapping[str, Any]:
        """Block for the next incoming message (up to `recv_timeout_s`).

        Raises:
            WsConnectionLost: on timeout or any transport/decode failure --
                the caller (`market_data.py`) treats this uniformly as "the
                connection is dead, reconnect".
        """
        return self._recv()

    def _send(self, payload: Mapping[str, Any]) -> None:
        if self._transport is None:
            raise RuntimeError("ExnovaWsClient: not connected")
        self._transport.send(json.dumps(payload))

    def _recv(self) -> Mapping[str, Any]:
        if self._transport is None:
            raise RuntimeError("ExnovaWsClient: not connected")
        try:
            raw = self._transport.recv(timeout=self._recv_timeout_s)
        except Exception as exc:  # noqa: BLE001 - normalized to one clean type
            raise WsConnectionLost(str(exc)) from exc

        try:
            return json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise WsConnectionLost(f"invalid JSON from transport: {exc}") from exc
