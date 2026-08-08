# botafuturo

A trading bot for the [Exnova](https://exnova.com) broker, built with a
hexagonal architecture (domain / ports / adapters) in Python.

## Scope (v1) — READ THIS FIRST

> **Paper-trading only.** In its current (v1) scope this project **does not
> place real-money trades**. All order execution goes through the `paper`
> adapter, which simulates fills against real or recorded market data. Real
> execution against Exnova's live/demo trading endpoints is explicitly out
> of scope until a future, separately-approved phase implements and audits
> the `exnova` execution adapter for that purpose.
>
> Until then, treat any Exnova connectivity in this project as **read-only
> market data / demo-account experimentation**, never as a source of real
> financial risk.

## Status

Early scaffolding stage. Domain logic, ports, and adapters are not
implemented yet — see the project's task list for the current phase.

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

   To also work on the Exnova adapter (needs `keyring` for credential
   storage), install the `exnova` extra as well:

   ```bash
   pip install -e ".[dev,exnova]"
   ```

3. Copy the environment template and fill in your **Exnova demo account**
   credentials (never your real-money account, and never commit this file):

   ```bash
   cp .env.example .env
   ```

4. Run the test suite:

   ```bash
   pytest
   ```

## Project layout

```
src/botafuturo/
├── domain/      # Pure business entities and rules (no I/O)
├── ports/       # Interfaces the domain depends on
├── adapters/    # Concrete implementations: exnova/, paper/, logging/
├── config/      # Settings loading (env vars, .env, keyring)
└── cli/         # Command-line entry points
tests/
├── unit/        # Fast, isolated unit tests
├── contract/    # Port/contract conformance tests
├── integration/ # Adapter tests against fakes or local services
├── architecture/# Hexagonal layering boundary enforcement
└── e2e/         # End-to-end paper-trading flow tests
docs/
└── spike-report.md  # Exnova protocol capture template (fill in before
                      # the Exnova adapter phase begins)
```
