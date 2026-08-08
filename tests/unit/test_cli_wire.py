"""Unit tests for `cli/wire.py` — the CLI composition root.

`build_paper_trading_session` is the ONLY function in this codebase (besides
`open_journal_for_report`, also in `cli/wire.py`) allowed to construct a
`PaperBrokerAdapter`/`JsonlTradeLog` directly. These tests prove it wires a
valid, fully-configured `TradingSession` + `JsonlTradeLog` pair from a
`Settings` instance and an injected `MarketDataPort` (here `FakeMarketData`,
standing in for a future real Exnova adapter).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from botafuturo.adapters.logging.journal import JsonlTradeLog
from botafuturo.adapters.logging.redaction import SecretRegistry
from botafuturo.cli.wire import build_paper_trading_session, open_journal_for_report
from botafuturo.config.settings import Settings
from botafuturo.domain.risk.manager import RiskManager
from botafuturo.domain.session import TradingSession
from botafuturo.domain.strategy.ma_crossover import MovingAverageCrossoverStrategy
from tests.fakes.market_data import FakeMarketData

_ASSET = "EURUSD"


@pytest.fixture()
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.delenv("EXNOVA_EMAIL", raising=False)
    monkeypatch.delenv("EXNOVA_PASSWORD", raising=False)
    monkeypatch.setenv("EXNOVA_EMAIL", "trader@example.com")
    monkeypatch.setenv("EXNOVA_PASSWORD", "hunter2")
    return Settings(_env_file=None)


def test_build_paper_trading_session_wires_a_valid_session_and_journal(
    settings: Settings, tmp_path: Path
) -> None:
    market_data = FakeMarketData()

    wired = build_paper_trading_session(
        settings, market_data, asset=_ASSET, journal_dir=tmp_path
    )

    assert isinstance(wired.session, TradingSession)
    assert wired.session.asset == _ASSET
    assert isinstance(wired.session.strategy, MovingAverageCrossoverStrategy)
    assert wired.session.strategy.fast_period == settings.sma_fast_period
    assert wired.session.strategy.slow_period == settings.sma_slow_period
    assert isinstance(wired.session.risk_manager, RiskManager)
    assert wired.session.stake == settings.stake_amount
    assert wired.session.expiry_s == settings.default_expiry_s
    assert wired.session.payout_rate == settings.payout_rate
    assert isinstance(wired.trade_log, JsonlTradeLog)
    assert isinstance(wired.registry, SecretRegistry)


def test_journal_file_lives_under_journal_dir_and_is_date_named(
    settings: Settings, tmp_path: Path
) -> None:
    market_data = FakeMarketData()
    wired = build_paper_trading_session(
        settings,
        market_data,
        asset=_ASSET,
        journal_dir=tmp_path,
        today=date(2026, 3, 4),
    )

    wired.trade_log.append({"order_id": "x", "ts": date(2026, 3, 4).isoformat()})

    expected_path = tmp_path / "2026-03-04.jsonl"
    assert expected_path.exists()


def test_registry_holds_configured_credentials_for_redaction(
    settings: Settings, tmp_path: Path
) -> None:
    market_data = FakeMarketData()

    wired = build_paper_trading_session(
        settings, market_data, asset=_ASSET, journal_dir=tmp_path
    )

    assert "hunter2" in wired.registry.values
    assert "trader@example.com" in wired.registry.values


def test_get_balance_reflects_configured_starting_balance(
    settings: Settings, tmp_path: Path
) -> None:
    market_data = FakeMarketData()

    wired = build_paper_trading_session(
        settings, market_data, asset=_ASSET, journal_dir=tmp_path
    )

    assert wired.session.get_balance() == settings.starting_balance


def test_open_journal_for_report_reads_back_appended_records(tmp_path: Path) -> None:
    writer = JsonlTradeLog(tmp_path / "2026-01-01.jsonl", SecretRegistry())
    writer.append({"order_id": "a", "ts": date(2026, 1, 1).isoformat()})

    reader = open_journal_for_report(tmp_path, date(2026, 1, 1))

    records = list(reader.read())
    assert [r["order_id"] for r in records] == ["a"]
