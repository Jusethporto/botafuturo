# Exnova Protocol Validation Spike — Capture Template

**Status: TEMPLATE — not yet filled in.**

This file is a checklist and empty table structure for the *human-operated*
step of Phase 0 (validation spike). No agent can complete this step alone:
it requires you to log into your **Exnova demo account** in a real browser
(or through a proxy) while capturing the actual network traffic, so that
the Exnova adapter (a later phase) is built against real, observed
behavior instead of guessed/hallucinated endpoints and message shapes.

Do not fill this in with assumptions. Every field below must come from
something you actually observed in devtools/mitmproxy. Leave a field
blank (or write `TODO`) rather than guessing.

## Why this matters

The Exnova adapter phase cannot start until this file is filled in (or the
captured data is otherwise handed to whoever implements that phase). Any
endpoint URL, payload shape, or WebSocket message schema in the design
docs is a placeholder until it is confirmed here.

## How to capture the traffic

Pick **one** of the two options below.

### Option A — Browser DevTools (simplest)

1. Open your browser (Chrome/Edge/Firefox) and open DevTools (`F12`).
2. Go to the **Network** tab. Make sure "Preserve log" is enabled.
3. If your browser supports it, add a **WS** (WebSocket) filter so you can
   see the WebSocket frames separately from normal HTTP requests.
4. Navigate to Exnova's site and **log in using your demo account only**
   (never your real-money credentials while capturing — treat this
   capture as something that might end up shared/reviewed).
5. Once logged in, open the trading interface so a live price feed starts
   streaming, and (optionally) place one small **binary option trade on
   the demo account** and let it settle.
6. For each request of interest (see checklist below), right-click it in
   the Network panel → "Copy" → "Copy as cURL" (for HTTP requests) or
   click into the WS connection and note the frames sent/received.

### Option B — mitmproxy (more complete, captures native app traffic too)

1. Install mitmproxy (`pip install mitmproxy` or your OS package manager).
2. Run `mitmweb` (or `mitmproxy` for the terminal UI) and configure your
   browser/OS to use it as an HTTP(S) proxy (mitmproxy prints the exact
   steps, including installing its CA certificate for HTTPS decryption).
3. Repeat the same login/trade flow as in Option A while mitmproxy is
   running, then use its UI to export the relevant flows (mitmweb lets
   you save individual flows or the whole capture).

## What to capture (checklist)

- [ ] **0.1 — Login/auth request**: the exact request Exnova's client
      sends to authenticate (method, URL, headers of interest, request
      body shape — with your actual credentials redacted/replaced before
      sharing), and the shape of the response (what identifies a
      successful login — token? cookie? session id?).
- [ ] **0.2a — WebSocket upgrade request**: the URL used for the WS
      handshake, and any query params / headers it needs (e.g. an auth
      token from the login step).
- [ ] **0.2b — First few WebSocket messages**: the first 5-10 messages
      exchanged right after the WS connection opens (both directions),
      to see any handshake/subscribe handshake pattern.
- [ ] **0.2c — Live price/quote message**: at least one full example of
      the message Exnova sends when a price/quote updates for an asset
      you're watching.
- [ ] **0.2d — Heartbeat / keep-alive pattern** (if observed): does the
      client or server send periodic ping/pong or heartbeat messages? At
      what interval?
- [ ] **0.2e (best effort) — Placed trade request/response**: the request
      sent when you place a binary option trade on the demo account, and
      the message(s) received when it settles (win/loss/payout).

## Findings — fill in below

### Base URLs

| Purpose | URL | Notes |
|---|---|---|
| Web app / login page | | |
| REST/HTTP API base | | |
| WebSocket endpoint | | |

### Auth endpoint

| Field | Value |
|---|---|
| Method | |
| URL | |
| Request headers of interest | |
| Request body shape (redact real credential values) | |
| Success response shape (token/cookie/session field name) | |
| Failure response shape | |

### WebSocket connection

| Field | Value |
|---|---|
| WS URL (with placeholder for any token/query param) | |
| Required headers/query params | |
| First messages sent by client after connect | |
| First messages received from server after connect | |

### WebSocket message schemas observed

| Event/message name | Direction (send/recv) | Example payload (redacted) | Notes |
|---|---|---|---|
| | | | |
| | | | |

### Heartbeat / keep-alive

| Field | Value |
|---|---|
| Observed? (yes/no) | |
| Direction | |
| Interval (seconds) | |
| Message shape | |

### Candle / quote message shape

```
# paste one full example JSON/text frame here, with any account-identifying
# fields redacted
```

### Placed trade request/response (best effort)

```
# request:


# response(s) while pending / on settlement:

```

## Next step

Once every checklist item above has at least a `TODO` or a real captured
value, this file is ready to hand to whoever implements the Exnova
adapter phase (a later phase in this project's task list). Until then,
that phase stays blocked — do not guess protocol details to unblock it.
