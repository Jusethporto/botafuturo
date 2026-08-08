"""End-to-end offline test: composition root -> session loop -> journal read/report.

Exercises the full v1 stack without any real broker/market-data adapter:
`cli/wire.py` builds a `TradingSession` wired to a `PaperBrokerAdapter` and a
`JsonlTradeLog`, `cli/run.py` drives it against `FakeMarketData` preloaded
with a candle sequence engineered to trigger exactly one MA-crossover
signal, and `cli/report.py`'s `summarize()` reads the resulting journal
back. This is the "Phase 11: E2E offline" scenario from the tasks list --
included in this PR because it validates the CLI wiring end-to-end and
depends on nothing from Phase 8 (the still-deferred Exnova adapter) or
Phase 10.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from botafuturo.cli.report import summarize
from botafuturo.cli.run import run_session
from botafuturo.cli.wire import build_paper_trading_session
from botafuturo.config.settings import Settings
from botafuturo.domain.models import Candle
from tests.fakes.market_data import FakeMarketData

_ASSET = "EURUSD"
_TIMEFRAME_S = 60
_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
# fast_period=2, slow_period=3 (via env below) => warmup_bars() == 4. This
# exact close sequence is the proven bullish-crossover fixture from
# tests/unit/test_ma_crossover_strategy.py::test_bullish_crossover_emits_call
# (flat "10"x4 then "12"), with one extra trailing candle ("14") so the
# opened position's 60s expiry is reached by the next candle and settles
# within this same finite stream.
_CLOSES = ["10", "10", "10", "10", "12", "14"]


def _candle(index: int, close: str) -> Candle:
    return Candle(
        asset=_ASSET,
        open_time=_T0 + timedelta(seconds=index * _TIMEFRAME_S),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("10"),
        timeframe_s=_TIMEFRAME_S,
    )


@pytest.fixture()
def crossover_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.delenv("EXNOVA_EMAIL", raising=False)
    monkeypatch.delenv("EXNOVA_PASSWORD", raising=False)
    monkeypatch.setenv("EXNOVA_EMAIL", "trader@example.com")
    monkeypatch.setenv("EXNOVA_PASSWORD", "hunter2")
    monkeypatch.setenv("SMA_FAST_PERIOD", "2")
    monkeypatch.setenv("SMA_SLOW_PERIOD", "3")
    return Settings(_env_file=None)


@pytest.mark.e2e
def test_full_offline_paper_trading_flow_records_at_least_one_sane_trade(
    crossover_settings: Settings, tmp_path
) -> None:
    candles = [_candle(i, close) for i, close in enumerate(_CLOSES)]
    market_data = FakeMarketData(candles=candles)

    wired = build_paper_trading_session(
        crossover_settings, market_data, asset=_ASSET, journal_dir=tmp_path
    )

    processed = run_session(wired.session, market_data, _ASSET, _TIMEFRAME_S)

    assert processed == len(_CLOSES)
    assert market_data.connected is False

    summary = summarize(wired.trade_log)
    assert summary.trade_count >= 1
    assert summary.trade_count == summary.win_count + summary.loss_count + summary.tie_count

    records = list(wired.trade_log.read())
    trade = records[0]
    assert trade["asset"] == _ASSET
    assert trade["outcome"] in {"win", "loss", "tie"}
    assert trade["order_id"]
    assert Decimal(str(trade["stake"])) == crossover_settings.stake_amount
    assert Decimal(str(trade["balance_after"])) >= Decimal("0")
