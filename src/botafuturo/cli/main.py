"""Minimal CLI entrypoint: `run` (paper-trading session loop) and `report`
(journal summary).

This is intentionally small -- a working, testable entrypoint shape per the
design, not a full-featured CLI. It never imports from `adapters/paper/` or
`adapters/logging/` directly: all adapter construction is delegated to
`cli/wire.py`, the composition root.

Documented limitation: the `run` command has no production `MarketDataPort`
implementation to plug in yet. The real Exnova adapter is Phase 8, and
Phase 8 is intentionally deferred pending the user's real-traffic
validation spike -- it is not part of this PR. The `--fake-data` flag makes
that limitation an explicit, deliberate acknowledgement at the call site
rather than a silent no-op; passing it still does not run anything real,
since wiring `tests.fakes.market_data.FakeMarketData` into a production
entrypoint would blur the test/production boundary (`tests/fakes` is
test-only code and is never imported by `src/botafuturo`). The composition
root (`botafuturo.cli.wire.build_paper_trading_session`) and session loop
(`botafuturo.cli.run.run_session`) that `run` would ultimately drive are
already fully implemented and exercised end-to-end by
`tests/e2e/test_offline_session.py`.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

from botafuturo.cli.report import print_summary, summarize
from botafuturo.cli.wire import open_journal_for_report

_DEFAULT_JOURNAL_DIR = Path("journal")


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
        "--fake-data",
        action="store_true",
        help=(
            "Required for now: there is no live Exnova market-data adapter "
            "yet (Phase 8, deferred). Passing this flag acknowledges that "
            "'run' cannot yet drive a real session."
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
    if not args.fake_data:
        parser.error(
            "'run' requires --fake-data: there is no live Exnova market-data "
            "adapter yet (Phase 8, deferred)."
        )

    print(
        "botafuturo run: no production MarketDataPort adapter is wired into "
        "this entrypoint yet -- the Exnova adapter is Phase 8, deferred "
        "pending a real-traffic validation spike. The composition root "
        "(botafuturo.cli.wire.build_paper_trading_session) and session loop "
        "(botafuturo.cli.run.run_session) are fully implemented and tested; "
        "wire a MarketDataPort implementation to them directly for now.",
        file=sys.stderr,
    )
    return 1


def _report_command(args: argparse.Namespace) -> int:
    trade_log = open_journal_for_report(args.journal_dir, args.date)
    summary = summarize(trade_log)
    print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
