# botafuturo

A trading bot for the [Exnova](https://exnova.com) broker, built with a
hexagonal architecture (domain / ports / adapters) in Python.

## Scope (v1) — READ THIS FIRST

> **Paper-trading only.** In its current (v1) scope this project **does not
> place real-money trades**. All order execution goes through the `paper`
> adapter, which simulates fills in-memory. Real execution against
> Exnova's live/demo trading endpoints is explicitly out of scope until a
> future, separately-approved phase implements and audits the `exnova`
> adapter for that purpose — see [Status](#status) below.
>
> This is not merely a disabled feature or a config flag: it is a
> **structural** guarantee, enforced by dedicated architecture tests (see
> [Safety guarantees](#safety-guarantees)). There is currently no
> order-submission code path against a real broker anywhere in this
> codebase.

## Status

Core architecture is implemented and tested: domain layer, ports, the
paper-trading broker adapter, structured logging with a credential-redaction
chokepoint, configuration/settings loading, a minimal CLI, and a full suite
of architecture-guarantee tests. **180 tests pass** across unit, contract,
integration, architecture, and e2e layers.

**Not yet built**: the real Exnova adapter (`src/botafuturo/adapters/exnova/`
is currently an empty package with only a docstring). That adapter is
blocked on a manual, human-operated validation spike — see
[`docs/spike-report.md`](docs/spike-report.md) — because it must be built
against real, observed Exnova protocol behavior instead of guessed endpoints
and message shapes. Until that spike is filled in, `botafuturo run` cannot
drive a real trading session end-to-end (see
[How to use the CLI today](#how-to-use-the-cli-today)).

## Architecture overview

Hexagonal (ports & adapters) architecture:

- **`domain/`** — pure business logic (trading session, P&L, settlement,
  risk management, strategies). No I/O, no network, no framework
  dependencies. This is what makes the domain layer fast and trivially
  unit-testable.
- **`ports/`** — `Protocol`-based interfaces the domain depends on
  (`BrokerPort`, `MarketDataPort`, `ClockPort`, `TradeLogPort`). The domain
  never depends on a concrete adapter, only on these contracts.
- **`adapters/`** — concrete implementations of the ports:
  - `paper/` — the only `BrokerPort` implementation that exists today. It
    simulates order placement/settlement fully in-memory: no network calls,
    no real broker call, no real money at risk. This is proven, not just
    documented — see [Safety guarantees](#safety-guarantees).
  - `logging/` — structured logging setup, the JSONL trade journal, and the
    credential-redaction chokepoint every log/journal record passes
    through.
  - `exnova/` — reserved for the real broker adapter. Currently empty
    (docstring only); deferred until the validation spike is done.
- **`config/`** — `pydantic-settings`-based `Settings`, defaults, and a
  single secret-unwrap chokepoint (`SecretProvider`) for reading credentials
  from the environment.
- **`cli/`** — the composition root (`wire.py`, which constructs adapters
  and wires them into the domain) plus the `run`/`report` entry points.

Because `BrokerPort` is a `Protocol` and the paper adapter is (by design,
and by test) the only class in `src/botafuturo` that structurally satisfies
it, there is currently no way for this codebase to place a real-money order.

## Setup

1. Create and activate a virtual environment (Python 3.11+):

   ```bash
   python -m venv .venv
   # Windows (PowerShell):
   .venv\Scripts\Activate.ps1
   # macOS/Linux:
   source .venv/bin/activate
   ```

2. Install the project in editable mode, with dev (test) dependencies:

   ```bash
   pip install -e ".[dev]"
   ```

   To also work on the (currently empty) Exnova adapter package later
   (needs `keyring` for credential storage), install the `exnova` extra as
   well:

   ```bash
   pip install -e ".[dev,exnova]"
   ```

3. Copy the environment template and fill in your **Exnova demo account**
   credentials (never your real-money account, and never commit this file):

   ```bash
   cp .env.example .env
   ```

   These credentials are validated by `Settings`
   (`src/botafuturo/config/settings.py`) as required fields even though no
   runnable code path uses them yet — `EXNOVA_EMAIL` / `EXNOVA_PASSWORD` map
   directly to `Settings.exnova_email` / `Settings.exnova_password`
   (`SecretStr`, never logged in plaintext — see
   [Safety guarantees](#safety-guarantees)).

## How to run tests

```bash
pytest -v
```

The suite (180 tests) is organized in layers, matching the `pytest` markers
declared in `pyproject.toml`:

| Layer | Path | What it checks |
|---|---|---|
| `unit` | `tests/unit/` | Fast, isolated tests of individual modules. |
| `contract` | `tests/contract/` | Every `BrokerPort`/`MarketDataPort`/`ClockPort`/`TradeLogPort` implementation (including fakes) honors its port's contract. |
| `integration` | `tests/integration/` | Adapters wired together against fakes (e.g. session + paper broker). |
| `architecture` | `tests/architecture/` | Hexagonal layering and financial-safety guarantees — see below. |
| `e2e` | `tests/e2e/` | A full offline paper-trading session, end to end. |

## How to use the CLI today

```bash
python -m botafuturo.cli.main report --journal-dir <dir> --date <YYYY-MM-DD>
```

`report` reads the JSONL trade journal for the given date out of
`--journal-dir` (default `journal/`) and prints a summary (trade count,
wins/losses/ties, win rate, net P&L).

```bash
python -m botafuturo.cli.main run --asset <SYMBOL> [--timeframe-s 60] [--journal-dir <dir>] --fake-data
```

`run` is **not runnable end-to-end outside of tests yet**: there is no
production `MarketDataPort` implementation wired into it (that is the
deferred Exnova adapter, Phase 8). Invoking it without `--fake-data` refuses
to run and explains why; even with `--fake-data` it currently exits with an
explanatory message rather than trading, since wiring a test-only fake
(`tests/fakes/market_data.py`) into the production entrypoint would blur the
test/production boundary. The composition root
(`botafuturo.cli.wire.build_paper_trading_session`) and the session loop
(`botafuturo.cli.run.run_session`) that `run` would ultimately drive are
already fully implemented and exercised end-to-end by
`tests/e2e/test_offline_session.py` — only the live data feed is missing.

## Project layout

```
src/botafuturo/
├── domain/        # Pure business entities and rules (session, P&L, settlement, risk, strategies) — no I/O
├── ports/         # Protocol interfaces the domain depends on (broker, market data, clock, trade log)
├── adapters/
│   ├── paper/     # The only BrokerPort implementation: in-memory order simulation, zero network capability
│   ├── logging/   # Structured logging, JSONL trade journal, and the credential-redaction chokepoint
│   └── exnova/    # Reserved for the real broker adapter — empty until the validation spike is done
├── config/        # Settings (pydantic-settings), defaults, and the single secret-unwrap chokepoint
└── cli/           # Composition root (wire.py) plus `run`/`report` entry points
tests/
├── unit/          # Fast, isolated unit tests
├── contract/      # Port/contract conformance tests (real adapters + fakes)
├── integration/   # Adapters wired together against fakes
├── architecture/  # Hexagonal layering + financial-safety guarantee tests
├── e2e/           # End-to-end offline paper-trading session tests
├── fakes/         # Test-only port implementations (never imported by src/)
└── fixtures/      # Shared test fixtures
docs/
└── spike-report.md  # Exnova protocol capture template — fill in before the Exnova adapter phase begins
```

## Safety guarantees

These are not just documentation claims — every one of them is enforced by
a dedicated, passing test in `tests/architecture/`:

**No real-money order code path can exist:**

- `test_broker_mode_single_member.py` — `BrokerMode` has exactly one member
  (`PAPER`); adding a live-trading mode requires a deliberate, reviewed
  change to this test.
- `test_only_paper_broker_implementation.py` — the paper adapter is
  structurally the *only* class under `src/botafuturo` that satisfies
  `BrokerPort`.
- `test_paper_adapter_import_boundary.py` — the paper adapter imports zero
  networking libraries and never imports the (deferred) Exnova adapter.
- `test_no_order_submission_surface.py` — a forward guard on the currently
  empty `adapters/exnova/` package: no `place`/`buy`/`sell`/`order`/
  `submit_order` function may be defined there yet, and nothing there may
  structurally satisfy `BrokerPort`.

**Credentials never leak to logs, the journal, or stdout:**

- `test_single_secret_unwrap.py` — every raw credential read
  (`os.environ`/`os.getenv`/`keyring.get_password`) is confined to
  `config/secrets.py`'s `SecretProvider`; nothing else in `src/botafuturo`
  is allowed to read one directly.
- `test_no_secret_leakage.py` — an end-to-end test that drives a full
  simulated trading session through the real composition root with
  sentinel credentials, then *adversarially* injects those same secrets
  into a log record and a journal record to prove the redaction chokepoint
  (`adapters/logging/redaction.py`) actually substitutes
  `***REDACTED***` — not merely that nothing happened to trigger it.

## Next steps

The Exnova adapter (real market data + eventually real order execution,
under its own future-approved scope) is blocked on you: fill in
[`docs/spike-report.md`](docs/spike-report.md) by capturing real Exnova
protocol traffic (login, WebSocket handshake, price/quote messages,
heartbeat, trade placement/settlement) from your **demo account**. Once
that's done, the next phase can build the adapter against observed reality
instead of guessed endpoints and message shapes.
