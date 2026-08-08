"""Unit tests for `cli/main.py` — the argparse entrypoint dispatch.

`--fake-data`'s exit-1/limitation-message path never touches `Settings()`/
`ExnovaMarketDataAdapter` (unchanged from PR7). The real (non-`--fake-data`)
path is exercised here entirely through monkeypatched collaborators
(`Settings`, `ExnovaMarketDataAdapter`, `build_paper_trading_session`,
`run_session`, all bound as names inside `botafuturo.cli.main`) -- no real
network/credentials are ever touched in this module.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import botafuturo.cli.main as main_module
from botafuturo.adapters.exnova.session_auth import LoginError
from botafuturo.adapters.exnova.ws_client import AuthenticationError
from botafuturo.adapters.logging.journal import JsonlTradeLog
from botafuturo.adapters.logging.redaction import SecretRegistry
from botafuturo.cli.main import main


class _FakeSettings:
    exnova_email = "sentinel-email"
    exnova_password = "sentinel-password"


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    run_session_result=None,
    run_session_raises: Exception | None = None,
    settings_raises: Exception | None = None,
):
    captured = {"adapter_args": None, "wire_args": None, "run_args": None}
    sentinel_market_data = object()
    sentinel_wired = SimpleNamespace(session=object(), trade_log=object(), registry=object())

    def fake_settings():
        if settings_raises is not None:
            raise settings_raises
        return _FakeSettings()

    def fake_adapter(email, password, asset, active_id):
        captured["adapter_args"] = {
            "email": email,
            "password": password,
            "asset": asset,
            "active_id": active_id,
        }
        return sentinel_market_data

    def fake_build(settings, market_data, asset, journal_dir):
        captured["wire_args"] = {
            "settings": settings,
            "market_data": market_data,
            "asset": asset,
            "journal_dir": journal_dir,
        }
        return sentinel_wired

    def fake_run_session(session, market_data, asset, timeframe_s):
        captured["run_args"] = {
            "session": session,
            "market_data": market_data,
            "asset": asset,
            "timeframe_s": timeframe_s,
        }
        if run_session_raises is not None:
            raise run_session_raises
        return run_session_result if run_session_result is not None else 0

    monkeypatch.setattr(main_module, "Settings", fake_settings)
    monkeypatch.setattr(main_module, "ExnovaMarketDataAdapter", fake_adapter)
    monkeypatch.setattr(main_module, "build_paper_trading_session", fake_build)
    monkeypatch.setattr(main_module, "run_session", fake_run_session)

    return captured, sentinel_market_data, sentinel_wired


def test_run_missing_active_id_argument_exits_nonzero(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["run", "--asset", "EURUSD"])

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "--active-id" in captured.err


def test_run_missing_active_id_argument_exits_nonzero_even_with_fake_data(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["run", "--asset", "EURUSD", "--fake-data"])

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "--active-id" in captured.err


def test_run_with_fake_data_flag_reports_deferred_adapter_limitation() -> None:
    exit_code = main(["run", "--asset", "EURUSD", "--active-id", "86", "--fake-data"])

    assert exit_code == 1


def test_run_missing_required_asset_argument_exits_nonzero() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["run", "--fake-data", "--active-id", "86"])

    assert exc_info.value.code == 2


def test_run_real_path_wires_exnova_adapter_and_drives_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    captured, sentinel_market_data, sentinel_wired = _install_fakes(
        monkeypatch, run_session_result=3
    )

    exit_code = main(
        [
            "run",
            "--asset",
            "EURUSD",
            "--active-id",
            "86",
            "--journal-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert captured["adapter_args"] == {
        "email": "sentinel-email",
        "password": "sentinel-password",
        "asset": "EURUSD",
        "active_id": 86,
    }
    assert captured["wire_args"]["asset"] == "EURUSD"
    assert captured["wire_args"]["market_data"] is sentinel_market_data
    assert captured["wire_args"]["journal_dir"] == tmp_path
    assert captured["run_args"]["session"] is sentinel_wired.session
    assert captured["run_args"]["market_data"] is sentinel_market_data
    assert captured["run_args"]["asset"] == "EURUSD"
    assert captured["run_args"]["timeframe_s"] == 60

    out = capsys.readouterr().out
    assert "Connecting to Exnova" in out
    assert "asset=EURUSD" in out
    assert "active_id=86" in out
    assert "PAPER-TRADING" in out


def test_run_real_path_catches_login_failure_and_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    _install_fakes(
        monkeypatch,
        run_session_raises=LoginError("Exnova login failed with HTTP status 401"),
    )

    exit_code = main(
        ["run", "--asset", "EURUSD", "--active-id", "86", "--journal-dir", str(tmp_path)]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "failed to connect to Exnova" in err
    assert "401" in err


def test_run_real_path_catches_ws_authentication_failure_and_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    _install_fakes(
        monkeypatch,
        run_session_raises=AuthenticationError("WS authentication failed"),
    )

    exit_code = main(
        ["run", "--asset", "EURUSD", "--active-id", "86", "--journal-dir", str(tmp_path)]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "failed to connect to Exnova" in err


def test_run_real_path_catches_transport_connection_failure_and_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    _install_fakes(
        monkeypatch,
        run_session_raises=ConnectionRefusedError("no route to host"),
    )

    exit_code = main(
        ["run", "--asset", "EURUSD", "--active-id", "86", "--journal-dir", str(tmp_path)]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "failed to connect to Exnova" in err


def test_run_real_path_lets_unrelated_settings_error_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BoomError(Exception):
        pass

    _install_fakes(monkeypatch, settings_raises=_BoomError("missing EXNOVA_EMAIL"))

    with pytest.raises(_BoomError):
        main(["run", "--asset", "EURUSD", "--active-id", "86"])


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
