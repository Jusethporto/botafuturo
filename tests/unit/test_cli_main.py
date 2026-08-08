"""Unit tests for `cli/main.py` — the argparse entrypoint dispatch.

`run` never needs real credentials in these tests: both its argument-error
path (`--fake-data` omitted) and its documented-limitation path
(`--fake-data` passed) exit before touching `Settings()`/`SecretProvider`.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from botafuturo.adapters.logging.journal import JsonlTradeLog
from botafuturo.adapters.logging.redaction import SecretRegistry
from botafuturo.cli.main import main


def test_run_without_fake_data_flag_exits_nonzero_via_argparse_error(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["run", "--asset", "EURUSD"])

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "--fake-data" in captured.err


def test_run_with_fake_data_flag_reports_deferred_adapter_limitation() -> None:
    exit_code = main(["run", "--asset", "EURUSD", "--fake-data"])

    assert exit_code == 1


def test_run_missing_required_asset_argument_exits_nonzero() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["run", "--fake-data"])

    assert exc_info.value.code == 2


def test_report_command_prints_summary_for_existing_journal(tmp_path: Path, capsys) -> None:
    trade_log = JsonlTradeLog(tmp_path / "2026-01-01.jsonl", SecretRegistry())
    trade_log.append(
        {
            "order_id": "a",
            "ts": date(2026, 1, 1).isoformat(),
            "outcome": "win",
            "pnl": "8.50",
        }
    )

    exit_code = main(["report", "--journal-dir", str(tmp_path), "--date", "2026-01-01"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Trade summary" in captured.out
    assert "100.00%" in captured.out


def test_report_command_handles_missing_journal_file_without_crashing(
    tmp_path: Path, capsys
) -> None:
    exit_code = main(["report", "--journal-dir", str(tmp_path), "--date", "2026-01-01"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "N/A" in captured.out


def test_report_command_requires_date_argument() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["report"])

    assert exc_info.value.code == 2


def test_no_command_exits_nonzero() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == 2
