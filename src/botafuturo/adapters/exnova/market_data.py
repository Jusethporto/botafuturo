"""`ExnovaMarketDataAdapter`: real-time `MarketDataPort` implementation
against the live Exnova WebSocket feed.

Scope (this PR / v1): read-only LIVE candle streaming only.

  * `history()` and `price_at()` intentionally raise `NotImplementedError`.
    The `get-candles` request/response shape needed for `history()` was
    seen in traffic during the validation spike but NOT deep-inspected
    with enough confidence to implement correctly (see
    `docs/spike-report.md`'s "Open items" section) -- guessing at an
    unobserved schema is out of scope for this PR. `price_at()` would need
    either that same capability or a live quote cache this PR does not
    build.
  * Order placement/settlement (`BrokerPort`) is explicitly OUT OF SCOPE
    for this module. See `tests/architecture/test_no_order_submission_surface.py`
    and `tests/architecture/test_only_paper_broker_implementation.py`,
    which this module must keep passing: no `place`/`buy`/`sell`/`order`/
    `submit_order` function may be defined anywhere under
    `adapters/exnova/`, and nothing here may structurally satisfy
    `BrokerPort`. Real trades stay paper-only (`PaperBrokerAdapter`) in
    v1; this adapter's only job is to feed REAL live prices into that
    paper-trading simulation.

`active_id`<->symbol resolution is also out of scope (see `mapping.py`'s
module docstring): the caller supplies both `asset` (a display symbol) and
`active_id` (the wire protocol's numeric instrument id) at construction
time, and this adapter only ever streams that one configured pair.

Reconnect/backoff: on any WS receive failure (timeout or transport error --
see `ws_client.WsConnectionLost`), this adapter yields one `GapMarker` for
the interrupted timeframe slot, waits `reconnect.backoff_delay(attempt)`
(exponential backoff with full jitter, capped at 60s), performs a full
fresh login + WS re-authenticate, re-subscribes, and resumes streaming.

Closed-bar detection (window-rollover buffering): a real live run
confirmed the server pushes `candle-generated` roughly once per SECOND
regardless of the subscribed `size` -- e.g. at `size:60` it repeats the
SAME `from`/`to` window (with `close`/`min`/`max` evolving) about 60
times before the window's real 60 seconds elapse and it moves to the next
one (see `docs/spike-report.md`). `to_candle()` stays a pure per-message
mapper and does NOT know whether a given push is the final state of its
window -- so `stream_closed_candles()` is responsible for closed-bar
detection: it keeps a single "in-progress candle" buffer (the latest
mapped `Candle` for the currently-open window) and only YIELDS a candle
once it observes a push for a NEW (different) `open_time`, at which point
it yields the previously buffered candle (that window's final, closed
state) and starts buffering the new one. A still-forming candle is never
yielded on its own -- not while pushes for it keep arriving, and not on
generator exhaustion (`disconnect()`) either, since it genuinely never
closed. The buffer is also discarded (not carried across) on every
reconnect, since the resumed stream may have missed that window's actual
close.
"""
from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Callable, Iterator, Optional, Sequence

from pydantic import SecretStr

from botafuturo.adapters.exnova import mapping, reconnect
from botafuturo.adapters.exnova.session_auth import HttpPost, _default_http_post, login
from botafuturo.adapters.exnova.ws_client import (
    DEFAULT_WS_URL,
    ExnovaWsClient,
    TransportFactory,
    WsConnectionLost,
    default_transport_factory,
)
from botafuturo.adapters.logging.redaction import SecretRegistry
from botafuturo.domain.models import Candle, Quote
from botafuturo.ports.market_data import GapMarker

_CANDLE_EVENT = "candle-generated"
_TIME_SYNC_EVENT = "timeSync"
_CANDLE_STREAM_REQUEST_ID = "candle-stream-1"

_NOT_IMPLEMENTED_HISTORY = (
    "ExnovaMarketDataAdapter.history() is not implemented in v1: the "
    "get-candles request/response shape was not captured with enough "
    "confidence during the validation spike (see docs/spike-report.md, "
    "'Open items'). A follow-up capture is required before implementing "
    "this; guessing at the schema is out of scope for this PR."
)
_NOT_IMPLEMENTED_PRICE_AT = (
    "ExnovaMarketDataAdapter.price_at() is not implemented in v1, for the "
    "same reason as history(): no confidently-captured historical "
    "quote/candle-fetch schema exists yet. See docs/spike-report.md."
)


class ExnovaMarketDataAdapter:
    """Live `MarketDataPort` implementation streaming candles from Exnova's
    real WebSocket feed for exactly one caller-configured `(asset,
    active_id)` pair."""

    def __init__(
        self,
        email: SecretStr,
        password: SecretStr,
        asset: str,
        active_id: int,
        *,
        ws_url: str = DEFAULT_WS_URL,
        transport_factory: TransportFactory = default_transport_factory,
        http_post: HttpPost = _default_http_post,
        idle_timeout_s: float = 5.0,
        registry: Optional[SecretRegistry] = None,
        rng: Optional[random.Random] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._email = email
        self._password = password
        self._asset = asset
        self._active_id = active_id
        self._http_post = http_post
        self._registry = registry
        self._rng = rng if rng is not None else random.Random()
        self._sleep = sleep
        self._ws = ExnovaWsClient(
            url=ws_url, transport_factory=transport_factory, recv_timeout_s=idle_timeout_s
        )
        self._connected = False

    def connect(self) -> None:
        """Log in (HTTP) and authenticate the WS connection. Idempotent."""
        if self._connected:
            return
        result = login(
            self._email, self._password, http_post=self._http_post, registry=self._registry
        )
        self._ws.connect(result.ssid.get_secret_value())
        self._connected = True

    def disconnect(self) -> None:
        """Close the WS connection. Idempotent."""
        if not self._connected:
            return
        self._ws.disconnect()
        self._connected = False

    def history(self, asset: str, timeframe_s: int, count: int) -> Sequence[Candle]:
        raise NotImplementedError(_NOT_IMPLEMENTED_HISTORY)

    def price_at(self, asset: str, at: datetime) -> Quote:
        raise NotImplementedError(_NOT_IMPLEMENTED_PRICE_AT)

    def stream_closed_candles(self, asset: str, timeframe_s: int) -> Iterator[Candle | GapMarker]:
        if asset != self._asset:
            raise ValueError(
                f"ExnovaMarketDataAdapter is configured for asset {self._asset!r}, "
                f"got {asset!r} -- construct a separate adapter per asset"
            )

        self.connect()
        self._subscribe_candles(timeframe_s)
        attempt = 0
        # The latest mapped `Candle` for the currently still-forming
        # window, or `None` if no push has been seen yet (fresh stream, or
        # just after a reconnect). See this module's docstring on
        # closed-bar detection -- never yielded until a push for a NEW
        # `open_time` is observed, proving this one has actually closed.
        pending_candle: Optional[Candle] = None

        while True:
            try:
                msg = self._ws.receive()
            except WsConnectionLost:
                attempt += 1
                # Discard rather than carry across: the resumed stream may
                # have missed this window's actual close, so whatever was
                # buffered must never be yielded as though it had closed.
                pending_candle = None
                yield GapMarker(
                    asset=asset,
                    timeframe_s=timeframe_s,
                    at=datetime.now(timezone.utc),
                    reason="reconnect",
                )
                self._reconnect(attempt)
                self._subscribe_candles(timeframe_s)
                continue

            name = msg.get("name")
            if name == _CANDLE_EVENT:
                body = msg.get("msg") or {}
                if body.get("active_id") == self._active_id:
                    attempt = 0
                    candle = mapping.to_candle(msg, asset)
                    if pending_candle is not None and candle.open_time != pending_candle.open_time:
                        # The window rolled over: `pending_candle` just
                        # closed (its final buffered state is this push's
                        # predecessor) -- yield it, then start buffering
                        # the new, now-current window. The new push itself
                        # is NOT yielded yet: it only becomes eligible once
                        # the window AFTER it closes, in turn.
                        closed_candle = pending_candle
                        pending_candle = candle
                        yield closed_candle
                    else:
                        # Either the first push ever seen, or another live
                        # update to the SAME still-forming window -- just
                        # replace the buffer with this newer state, don't
                        # yield yet.
                        pending_candle = candle
            elif name == _TIME_SYNC_EVENT:
                attempt = 0
            # Any other push (e.g. `front`) is informational for this
            # stream and is silently ignored -- see docs/spike-report.md.

    def _subscribe_candles(self, timeframe_s: int) -> None:
        # `active_id`/`size` MUST be nested inside a `routingFilters` object
        # inside `params`, confirmed via a real browser capture (see
        # docs/spike-report.md's "CRITICAL -- corrected 2026-08-08" entry).
        # A flat `params={"active_id": ..., "size": ...}` is silently
        # ignored by the server: no error is returned, the subscription
        # request itself succeeds, but zero matching `candle-generated`
        # pushes ever arrive. This was caught by a real live run (bot
        # connected + authenticated fine, but no candle data for 4+
        # minutes despite healthy `timeSync` heartbeats) and confirmed by a
        # follow-up capture comparing our subscribe call against the real
        # client's.
        #
        # Note: the real client's `candle-generated` subscribe message has
        # no `version` key at the `msg` level (unlike e.g. `level-updated`,
        # which does send `"version":"1.0"`). `ExnovaWsClient.subscribe()`
        # always adds `version` unconditionally for every event -- whether
        # an extra, unused `version` key breaks this specific subscription
        # is unconfirmed, so we deliberately leave `subscribe()`'s generic
        # envelope unchanged rather than adding a special case for one
        # event: the `routingFilters` wrapper below is the confirmed,
        # load-bearing fix.
        self._ws.subscribe(
            _CANDLE_EVENT,
            _CANDLE_STREAM_REQUEST_ID,
            params={"routingFilters": {"active_id": self._active_id, "size": timeframe_s}},
        )

    def _reconnect(self, attempt: int) -> None:
        delay = reconnect.backoff_delay(attempt, rng=self._rng)
        self._sleep(delay)
        self._ws.disconnect()
        self._connected = False
        self.connect()
