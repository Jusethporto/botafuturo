"""Unit tests for `cli/report.py` — `summarize()`/`print_summary()`."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from botafuturo.adapters.logging.journal import JsonlTradeLog
from botafuturo.adapters.logging.redaction import SecretRegistry
from botafuturo.cli.report import print_summary, summarize


def _log(tmp_path: Path) -> JsonlTradeLog:
    return JsonlTradeLog(tmp_path / "trades.jsonl", SecretRegistry())


def test_summarize_computes_counts_win_rate_and_net_pnl_excluding_ties(
    tmp_path: Path,
) -> None:
    trade_log = _log(tmp_path)
    trade_log.append(
        {"order_id": "a", "ts": date(2026, 1, 1).isoformat(), "outcome": "win", "pnl": "8.50"}
    )
    trade_log.append(
        {"order_id": "b", "ts": date(2026, 1, 1).isoformat(), "outcome": "loss", "pnl": "-10.00"}
    )
    trade_log.append(
        {"order_id": "c", "ts": date(2026, 1, 1).isoformat(), "outcome": "tie", "pnl": "0"}
    )
    trade_log.append(
        {"order_id": "d", "ts": date(2026, 1, 1).isoformat(), "outcome": "win", "pnl": "8.50"}
    )

    summary = summarize(trade_log)

    assert summary.trade_count == 4
    assert summary.win_count == 2
    assert summary.loss_count == 1
    assert summary.tie_count == 1
    # win_rate excludes ties from the denominator: 2 wins / (2 wins + 1 loss)
    assert summary.win_rate == Decimal("2") / Decimal("3")
    assert summary.net_pnl == Decimal("7.00")


def test_summarize_zero_trades_reports_none_win_rate_and_zero_pnl(tmp_path: Path) -> None:
    trade_log = _log(tmp_path)

    summary = summarize(trade_log)

    assert summary.trade_count == 0
    assert summary.win_count == 0
    assert summary.loss_count == 0
    assert summary.tie_count == 0
    assert summary.win_rate is None
    assert summary.net_pnl == Decimal("0")


def test_summarize_all_ties_reports_none_win_rate_not_zero(tmp_path: Path) -> None:
    trade_log = _log(tmp_path)
    trade_log.append(
        {"order_id": "a", "ts": date(2026, 1, 1).isoformat(), "outcome": "tie", "pnl": "0"}
    )

    summary = summarize(trade_log)

    # None (no decisive trades yet) is distinct from 0 (a 0% win rate).
    assert summary.win_rate is None


def test_print_summary_handles_zero_trades_without_crashing(tmp_path: Path, capsys) -> None:
    trade_log = _log(tmp_path)
    summary = summarize(trade_log)

    print_summary(summary)

    captured = capsys.readouterr()
    assert "N/A" in captured.out


def test_print_summary_prints_win_rate_as_percentage(tmp_path: Path, capsys) -> None:
    trade_log = _log(tmp_path)
    trade_log.append(
        {"order_id": "a", "ts": date(2026, 1, 1).isoformat(), "outcome": "win", "pnl": "8.50"}
    )
    summary = summarize(trade_log)

    print_summary(summary)

    captured = capsys.readouterr()
    assert "100" in captured.out
