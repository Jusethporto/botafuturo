# Exnova Protocol Validation Spike — Findings

**Status: CAPTURED — real findings from a live demo-account session.**

Captured via mitmproxy (Option B) on 2026-08-08, against the user's real
Exnova **demo** account. Two real binary-option ("turbo") trades were
placed and settled during capture (one loss, one win), confirming the
full order lifecycle end to end. All values below are real, observed
values with account-identifying/secret fields redacted per the notes on
each section. Raw `ssid`/session-token values are intentionally **not**
recorded anywhere in this file — they are short-lived and must be
obtained fresh per session via the login flow documented below, never
hardcoded.

**Confirmed key finding**: the WebSocket connection is redirected (via
the `front` message, see below) to a `*.quadcode.tech` backend host.
Quadcode is the known infrastructure provider behind IQ Option's
platform, so Exnova runs on the **same backend/protocol family as IQ
Option** — the "adapt an IQ-Option-family library" branch from the
original proposal's open question is now the more concrete path (though
the JSON message envelope observed below can also be implemented
directly, without depending on any third-party library, if preferred for
supply-chain/maintenance reasons — see recommendation at the bottom).

## Base URLs

| Purpose | URL | Notes |
|---|---|---|
| Web app / login page | `https://trade.exnova.com/en/login` | |
| REST/HTTP API base | `https://api.trade.exnova.com` | versioned paths: `/v1/`, `/v2/`, `/v4/`, `/v5/` coexist |
| WebSocket endpoint (initial) | `wss://ws.trade.exnova.com/echo/websocket` | client connects here first |
| WebSocket endpoint (assigned) | e.g. `ws04.ws.prod.sc-ams-1b.quadcode.tech` | server pushes the *actual* regional server to use via the `front` message right after auth; observed value will vary by region/session — treat as dynamic, never hardcode a specific `wsNN` host |

## Auth endpoint

| Field | Value |
|---|---|
| Method | `POST` |
| URL | `https://api.trade.exnova.com/v2/login` |
| Request headers of interest | `Content-Type: application/json`, `Accept: application/json`, `Origin: https://trade.exnova.com` |
| Request body shape | `{"identifier": "<email>", "password": "<password>"}` |
| Success response shape | `{"code":"success","company_id":15,"created_at":<unix_ts>,"ssid":"<session_id>","token":"<token>","user_id":<int>}` — **`ssid` is the credential the WebSocket auth step needs** |
| Failure response shape | not captured this session (login succeeded on first attempt) — TODO if needed later |

No 2FA/MFA prompt was encountered for this account; if the user's account
has MFA enabled, the login flow may differ (a follow-up spike would be
needed for that path).

## WebSocket connection

| Field | Value |
|---|---|
| WS URL | `wss://ws.trade.exnova.com/echo/websocket` (no query params observed — auth happens via the first message, not the URL) |
| Required headers/query params | none beyond the standard WS upgrade headers browsers set automatically |
| First message sent by client after connect | `{"name":"authenticate","msg":{"ssid":"<ssid from login>","protocol":3,"client_session_id":""}}` |
| First messages received from server after connect | 1. `{"name":"authenticated","msg":true,"client_session_id":"<uuid>","request_id":""}` — confirms auth succeeded.<br>2. `{"name":"front","msg":"<regional-ws-host>","session_id":"<numeric id>"}` — the server's suggested regional WS host (observed but the client did **not** appear to reconnect to it in this session — the original `ws.trade.exnova.com` connection kept working for the whole session; treat the `front` message as informational/optional for v1) |

## Message envelope (applies to almost everything after auth)

Every command the client sends and almost every server push follows this
shape:

```json
// client -> server (request)
{"name": "sendMessage", "request_id": "<client-chosen id>", "msg": {
  "name": "<namespaced.command-name>", "version": "<e.g. 1.0 or 2.0>",
  "body": { /* command-specific */ }
}}

// or, for subscriptions:
{"name": "subscribeMessage", "request_id": "<id>", "msg": {
  "version": "1.0", "name": "<event-name>", "params": { /* optional filters */ }
}}
// symmetric "unsubscribeMessage" to stop a subscription

// server -> client (response to a sendMessage, matched by request_id)
{"request_id": "<same id>", "name": "<response-type, often the bare command name>",
 "msg": { /* response payload */ }, "status": 2000}

// server -> client (unsolicited push for a subscribed event)
{"name": "<event-name>", "microserviceName": "<owning service, e.g. quotes|portfolio>",
 "msg": { /* event payload */ }}
```

`request_id` is client-generated (observed as both small sequential
integers like `"195"` and long numeric strings) and is only used to
correlate a `sendMessage`/`subscribeMessage` call with its direct
response — it is **not** required to be globally unique across the
session, just unique enough to disambiguate concurrently in-flight calls.

## WebSocket message schemas observed

| Event/message name | Direction | Example payload (redacted) | Notes |
|---|---|---|---|
| `authenticate` | send | `{"name":"authenticate","msg":{"ssid":"***","protocol":3,"client_session_id":""}}` | first message, must be sent immediately after connect |
| `authenticated` | recv | `{"name":"authenticated","msg":true,"client_session_id":"<uuid>","request_id":""}` | confirms session is authenticated |
| `front` | recv | `{"name":"front","msg":"<host>","session_id":"<id>"}` | informational regional-host hint, see above |
| `timeSync` | recv | (no payload of interest — heartbeat) | see Heartbeat section |
| `balances.get-balances` (send) / `balances` (recv) | both | recv: `{"request_id":"...","name":"balances","msg":[{"id":1248245156,"type":4,"amount":10000,"bonus_amount":0,"currency":"USD","is_fiat":true,"is_marginal":true,"auth_amount":0}, ...],"status":2000}` | `type: 4` = **demo/practice balance** (confirmed — this account's demo USD balance). `type: 1` = real-money balance (observed as a 0-balance COP account for this user). `amount` appears to be in the smallest currency unit **x100** (e.g. `10000` = $100.00) — **unconfirmed with full certainty, verify against the UI's displayed balance before trusting in code** |
| `binary-options.open-option` | send | `{"name":"sendMessage","request_id":"195","msg":{"name":"binary-options.open-option","version":"2.0","body":{"user_balance_id":1248245156,"active_id":86,"option_type_id":3,"direction":"call","expired":1786214520,"refund_value":0,"price":1000.0,"value":984275,"profit_percent":87}}}` | **the order-placement call.** `active_id` identifies the instrument (86 observed for the asset traded this session — an `active_id`↔symbol mapping table was not captured, needs its own lookup call, e.g. `get-initialization-data` or `digital-option-instruments.get-underlying-list`, seen in the traffic but not deep-inspected this round). `option_type_id: 3` = "turbo" (short 1-5min binary options — matches this project's scope). `direction`: `"call"` or `"put"`. `expired`: unix timestamp of expiry. `price`: stake, same x100-style scaling as balances. `profit_percent`: the *displayed* payout percent (87 here) |
| `option` | recv | `{"request_id":"195","name":"option","msg":{"user_id":...,"id":14147910497,"price":1000,"exp":1786214520,"created":1786214459,"type":"turbo","act":86,"direction":"call","exp_value":984275,"profit_income":187,"profit_return":0,...},"status":2000}` | order ack. `id` here is the option/order id — needed to correlate with the later settlement push |
| `position-changed` (subscribed via `portfolio.position-changed`) | recv | see below, `status: "open"` while pending, `status: "closed"` at settlement | **this is the settlement event** — see full example below |
| `candle-generated` (subscribed via `subscribeMessage::candle-generated`) | recv | `{"name":"candle-generated","microserviceName":"quotes","msg":{"active_id":86,"size":1,"at":<ns ts>,"from":<unix s>,"to":<unix s>,"id":<candle id>,"open":0.984425,"close":0.984425,"min":0.984425,"max":0.984425,"ask":0.98443,"bid":0.98442,"volume":0,"phase":"T"}}` | live price stream, very high frequency (~1 msg/sec at `size:1`, i.e. 1-second candles; 777 of these arrived during a ~5 minute session) |
| `positions-state` (subscribed) | recv | `{"name":"positions-state","microserviceName":"portfolio","msg":{"positions":[{"id":"...","instrument_type":"turbo-option","sell_profit":448.8,"margin":1000,"current_price":0.984275,"pnl":-551.2,"pnl_net":-551.2,"open_price":0.984275,"expected_profit":1000,...}],"subscription_id":"...","user_id":...,"expires_in":59}}` | periodic live mark-to-market of the still-open position (not the final settlement) |
| `get-candles` (send) / `candles` (recv) | both | not deep-inspected this round | historical candle fetch — needed for strategy warm-up, worth a follow-up capture focused on this call's exact params |

### Settlement — full example (the most important schema for this project)

Captured for both trades placed this session (one loss, one win), which
confirms the schema is stable across outcomes:

```json
// LOSS trade
{
  "name": "position-changed",
  "microserviceName": "portfolio",
  "msg": {
    "id": "<position id>",
    "external_id": 14147910497,
    "active_id": 86,
    "instrument_type": "turbo-option",
    "status": "closed",
    "open_time": 1786214459878,
    "open_quote": 0.984275,
    "invest": 1000,
    "close_quote": 0.984195,
    "close_reason": "loose",
    "close_time": 1786214520000,
    "close_profit": 0,
    "pnl": -1000,
    "pnl_realized": -1000,
    "pnl_net": -1000
  }
}

// WIN trade
{
  "name": "position-changed",
  "microserviceName": "portfolio",
  "msg": {
    "id": "<position id>",
    "external_id": 14147912586,
    "active_id": 86,
    "instrument_type": "turbo-option",
    "status": "closed",
    "open_time": 1786214520323,
    "open_quote": 0.984195,
    "invest": 2000,
    "close_quote": 0.984285,
    "close_reason": "win",
    "close_time": 1786214580000,
    "close_profit": 3740,
    "pnl": 1740,
    "pnl_realized": 1740,
    "pnl_net": 1740
  }
}
```

**This directly validates this project's existing domain P&L model**
(`domain/pnl.py::pnl_for`): for the WIN trade, `invest=2000`,
`close_profit=3740` (stake + profit returned), `pnl=1740` — and
`1740 / 2000 = 0.87`, matching the `profit_percent: 87` sent at order
placement. This is *exactly* `pnl_for(WIN, stake, payout_rate)` =
`stake * payout_rate` with `payout_rate = 0.87` for this instrument at
this moment. **Important refinement for the design**: `profit_percent`
is per-instrument and returned by the server at order-placement time
(inside the `option` ack, as `profit_income`, observed as `187` —
i.e. `100 + displayed_percent`), not a fixed global constant — the
config default (`payout_rate = 0.85`) should be treated as a
fallback/simulation default only; the real adapter should read the
actual server-quoted percent per order and use *that* for settlement
math, not the local config value. This is a design refinement to raise
in a future task, not a blocker.

The `raw_event.binary_options_option_changed1` sub-object (present on
both examples above, omitted here for brevity) carries the same
information plus a `"result": "win"` / `"result": "loose"` field —
either `close_reason` or `raw_event...result` can be used as the
win/loss/tie source of truth; a tie (`close_quote == open_quote`) was
not observed this session and its exact `close_reason` string value is
still a **TODO** for a future capture.

## Heartbeat / keep-alive

| Field | Value |
|---|---|
| Observed? | Yes |
| Direction | Server → client |
| Interval | ~1 second (292 `timeSync` pushes observed over roughly a 5-minute session) |
| Message shape | `{"name":"timeSync","msg":<server unix ms timestamp, as a bare number>}` (exact payload not deep-inspected — it's a lightweight clock-sync tick, not something the client needs to respond to) |

No explicit client-sent ping/pong was observed; the browser's WebSocket
implementation handles the protocol-level ping/pong transparently, and
`timeSync` appears to be an application-level tick, not a
connection-liveness mechanism the adapter needs to implement itself
beyond noticing if it stops arriving (which would indicate a dead
connection, same signal as any other silence-based reconnect trigger).

## Placed trade request/response

See the full **Message envelope**, **`binary-options.open-option`**, and
**Settlement** sections above — captured in full for both a losing and a
winning trade.

## Open items for a follow-up capture (not blocking, but worth noting)

- `active_id` ↔ instrument-symbol mapping (e.g. which `active_id` is
  "EURUSD-OTC" vs the `86` observed here) — needs one more capture
  focused on the asset-list/initialization call.
- Exact balance amount scaling (x100 assumption above is very likely
  correct for a Quadcode-family platform but should be double-checked
  against the UI's displayed number before the adapter trusts it).
- A tie/push outcome's exact `close_reason` string (not observed this
  session — only win/loss occurred).
- The `get-candles`/`candles` request/response shape for historical
  warm-up data (seen in traffic, not deep-inspected).
- Whether the client should proactively reconnect to the `front`-provided
  regional host, or whether staying on `ws.trade.exnova.com` for the
  whole session (as observed) is the normal/supported pattern.

## Recommendation for the Exnova adapter implementation

Given the message envelope is simple, stable, and now fully documented
above for the exact commands this project needs (auth, balance,
open-option, settlement subscription, candle subscription), **building a
small bespoke WebSocket client directly against this captured protocol
(Approach 1 from the original proposal) is now low-risk** — there is no
remaining need to adapt an unofficial IQ-Option-family library
(Approach 2), since the actual, current Exnova/Quadcode message shapes
are captured firsthand above rather than assumed from a different
platform's client. This avoids taking on an unmaintained third-party
dependency for a handful of well-understood JSON messages over one
WebSocket connection.

## Next step

This file now has real captured findings for every checklist item that
matters for v1 scope (binary options, turbo/short expiry, paper-trading
settlement math). Phase 8 (the real Exnova adapter) is unblocked and can
proceed using the schemas documented above, built directly against this
protocol rather than any third-party library.
