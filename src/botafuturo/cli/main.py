"""Minimal CLI entrypoint: `run` (paper-trading session loop) and `report`
(journal summary).

This is intentionally small -- a working, testable entrypoint shape per the
design, not a full-featured CLI. It never imports from `adapters/paper/` or
`adapters/logging/` directly: all adapter construction beyond `MarketDataPort`
is delegated to `cli/wire.py`, the composition root.

`ExnovaMarketDataAdapter` (real-time `MarketDataPort` implementation) IS
constructed directly here, deliberately -- see `cli/wire.py`'s module
docstring: `MarketDataPort` is the one collaborator the composition root
never constructs itself, precisely so the caller (this module) decides which
implementation to plug in. `--fake-data` remains a deliberate, non-functional
acknowledgement (per PR7's original design decision): wiring the test-only
`tests.fakes.market_data.FakeMarketData` into a production entrypoint would
blur the test/production boundary, so passing `--fake-data` still prints a
limitation message and exits 1 rather than trading. Without `--fake-data`,
`run` now constructs a real `ExnovaMarketDataAdapter` from `Settings` and
drives a genuine paper-trading session against LIVE Exnova prices --
`--active-id` (see its `--help` text) is required because there is no
symbol<->`active_id` lookup table yet (see `docs/spike-report.md`'s "Open
items"). Order execution stays 100% simulated via `PaperBrokerAdapter`
(wired by `cli/wire.py`) in both cases -- this module never constructs a
`BrokerPort` implementation.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

from botafuturo.adapters.exnova.market_data import ExnovaMarketDataAdapter
from botafuturo.adapters.exnova.session_auth import LoginError
from botafuturo.adapters.exnova.ws_client import AuthenticationError, WsConnectionLost
from botafuturo.cli.report import print_summary, summarize
from botafuturo.cli.run import run_session
from botafuturo.cli.wire import build_paper_trading_session, open_journal_for_report
from botafuturo.config.settings import Settings

_DEFAULT_JOURNAL_DIR = Path("journal")

#: Connection/auth failure types expected from `ExnovaMarketDataAdapter`
#: (raised via `run_session`'s call to `market_data.connect()`): a failed
#: HTTP login, a failed WS `authenticate` handshake, a dead/unreachable WS
#: connection mid-stream, or a raw transport-level connection error (e.g.
#: `ConnectionRefusedError`, a DNS failure) from opening the socket itself.
#: Anything else (a bug, a domain error) is intentionally NOT caught here
#: and surfaces as an unhandled traceback.
_EXNOVA_CONNECTION_ERRORS = (LoginError, AuthenticationError, WsConnectionLost, OSError)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="botafuturo")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="Run a paper-trading session against a market data source."
    )
    run_parser.add_argument("--asset", required=True, help="Instrument to trade, e.g. EURUSD.")
    run_parser.add_argument("--timeframe-s", type=int, default=60)
    run_parser.add_argument("--journal-dir", type=Path, default=_DEFAULT_JOURNAL_DIR)
    run_parser.add_argument(
        "--active-id",
        type=int,
        required=True,
        help=(
            "Numeric Exnova 'active_id' for the instrument to trade (e.g. 86 "
            "was observed for one asset during the validation spike). There "
            "is no symbol<->active_id lookup table yet -- see "
            "docs/spike-report.md's 'Open items' -- so you must currently "
            "supply this id directly. Find it by observing a network "
            "capture of the Exnova web app's WebSocket traffic (the "
            "candle-generated/subscribeMessage payloads carry it)."
        ),
    )
    run_parser.add_argument(
        "--fake-data",
        action="store_true",
        help=(
            "Deliberate non-functional acknowledgement: there is no "
            "production FakeMarketData-equivalent wired for real "
            "interactive use (tests/fakes stays test-only). Passing this "
            "flag still does not run anything real -- it prints a "
            "limitation message and exits. Omit this flag to actually "
            "connect to real, live Exnova market data (paper-trading only; "
            "order execution stays fully simulated)."
        ),
    )

    report_parser = subparsers.add_parser("report", help="Summarize a trade journal.")
    report_parser.add_argument("--journal-dir", type=Path, default=_DEFAULT_JOURNAL_DIR)
    report_parser.add_argument(
        "--date",
        type=date.fromisoformat,
        required=True,
        help="Journal file date, YYYY-MM-DD.",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return _run_command(args, parser)
    return _report_command(args)


def _run_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.fake_data:
        print(
            "botafuturo run: --fake-data was passed, but there is no "
            "production FakeMarketData-equivalent wired for real "
            "interactive use (tests/fakes stays test-only) -- this remains "
            "a deliberate non-functional acknowledgement, per PR7's "
            "original design decision. The composition root "
            "(botafuturo.cli.wire.build_paper_trading_session) and session "
            "loop (botafuturo.cli.run.run_session) are fully implemented "
            "and tested; omit --fake-data to actually connect to real, "
            "live Exnova market data instead.",
            file=sys.stderr,
        )
        return 1

    print(
        f"Connecting to Exnova (asset={args.asset}, active_id={args.active_id})... "
        "this is a PAPER-TRADING session -- no real money orders will ever "
        "be placed."
    )
    try:
        settings = Settings()
        market_data = ExnovaMarketDataAdapter(
            settings.exnova_email,
            settings.exnova_password,
            args.asset,
            args.active_id,
        )
        wired = build_paper_trading_session(settings, market_data, args.asset, args.journal_dir)
        run_session(wired.session, market_data, args.asset, args.timeframe_s)
    except _EXNOVA_CONNECTION_ERRORS as exc:
        print(f"botafuturo run: failed to connect to Exnova: {exc}", file=sys.stderr)
        return 1

    return 0


def _report_command(args: argparse.Namespace) -> int:
    trade_log = open_journal_for_report(args.journal_dir, args.date)
    summary = summarize(trade_log)
    print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
