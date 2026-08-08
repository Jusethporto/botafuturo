"""Unit tests for `cli/wire.py` — the CLI composition root.

`build_paper_trading_session` is the ONLY function in this codebase (besides
`open_journal_for_report`, also in `cli/wire.py`) allowed to construct a
`PaperBrokerAdapter`/`JsonlTradeLog` directly. These tests prove it wires a
valid, fully-configured `TradingSession` + `JsonlTradeLog` pair from a
`Settings` instance and an injected `MarketDataPort` (here `FakeMarketData`,
standing in for a future real Exnova adapter).
"""
from __future__ import annotations

import io
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from botafuturo.adapters.logging.journal import JsonlTradeLog
from botafuturo.adapters.logging.redaction import SecretRegistry
from botafuturo.cli.wire import build_paper_trading_session, open_journal_for_report
from botafuturo.config.settings import Settings
from botafuturo.domain.models import Direction, OrderAck, OrderRequest, Outcome, Trade
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


def _trade(outcome: Outcome, pnl: str, balance_after: str) -> Trade:
    opened_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    request = OrderRequest(
        asset=_ASSET,
        direction=Direction.CALL,
        stake=Decimal("10"),
        expiry_s=60,
        opened_at=opened_at,
        payout_rate=Decimal("0.85"),
    )
    ack = OrderAck(
        order_id="order-1",
        request=request,
        expiry_at=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
        entry_price=Decimal("100"),
    )
    return Trade(
        ack=ack,
        expiry_price=Decimal("101"),
        outcome=outcome,
        pnl=Decimal(pnl),
        balance_after=Decimal(balance_after),
    )


def test_log_trade_logs_an_info_record_with_outcome_and_pnl(
    settings: Settings, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    market_data = FakeMarketData()
    wired = build_paper_trading_session(
        settings, market_data, asset=_ASSET, journal_dir=tmp_path
    )
    trade = _trade(Outcome.WIN, "8.5", "1008.5")

    with caplog.at_level(logging.INFO, logger="botafuturo.cli.wire"):
        wired.session.log_trade(trade)

    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(info_records) == 1
    message = info_records[0].getMessage()
    assert "win" in message
    assert "8.5" in message
    assert "1008.5" in message


def test_log_trade_info_record_passes_through_the_redaction_chokepoint(
    settings: Settings, tmp_path: Path
) -> None:
    """`build_paper_trading_session` installs `RedactingFilter` (via
    `configure()`) on the root logger/handler BEFORE `log_trade`'s new
    `logger.info(...)` call ever fires. This proves that new call is not a
    bypass of the PR5/PR8 redaction chokepoint: an adversarial secret probed
    through the SAME logger `log_trade` uses is substituted with the
    redaction marker instead of appearing verbatim -- exactly like every
    other logger in this codebase (mirrors the pattern in
    `tests/architecture/test_no_secret_leakage.py`, minus the full session
    drive).
    """
    market_data = FakeMarketData()
    wired = build_paper_trading_session(
        settings, market_data, asset=_ASSET, journal_dir=tmp_path
    )
    secret = settings.exnova_password.get_secret_value()

    # Attach a plain, non-redacting handler AFTER `configure()` has already
    # installed the production redacting handler, so this handler observes
    # each record's message post-filter -- the same ordering the existing
    # e2e leakage test relies on.
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(handler)
    try:
        # Adversarial probe through the exact same logger `log_trade` uses
        # (`botafuturo.cli.wire`), proving the chokepoint actively
        # substitutes rather than this new call site being unfiltered.
        logging.getLogger("botafuturo.cli.wire").info(
            "probe leaked_password=%s", secret
        )
        wired.session.log_trade(_trade(Outcome.LOSS, "-10", "990"))
    finally:
        logging.getLogger().removeHandler(handler)

    log_text = stream.getvalue()
    assert secret not in log_text
    assert "***REDACTED***" in log_text
    assert "loss" in log_text  # the real log_trade call still went through
