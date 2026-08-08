"""CLI composition root.

This module is the ONLY module under `botafuturo.cli` (and one of the only
modules in the whole codebase) allowed to:

  1. Import from `botafuturo.adapters.paper` and `botafuturo.adapters.logging`.
  2. Construct a `PaperBrokerAdapter` directly.

Every other CLI module receives its collaborators wired here, through
dependency injection, rather than constructing adapters itself -- that is
what makes it a "composition root" rather than just another module.

`MarketDataPort` is deliberately the one collaborator this module does NOT
construct: it is passed in by the caller (see `build_paper_trading_session`),
so the caller decides whether to plug in `tests.fakes.market_data.FakeMarketData`
(the only option available today) or a future real Exnova market-data
adapter (Phase 8, deferred pending the user's real-traffic validation
spike) without this module -- or any of `TradingSession`, `RiskManager`, or
`MovingAverageCrossoverStrategy` -- ever changing. That injection point is
exactly the swappability the hexagonal/ports-and-adapters design calls for.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from botafuturo.adapters.logging.journal import JsonlTradeLog
from botafuturo.adapters.logging.logging_setup import configure
from botafuturo.adapters.logging.redaction import SecretRegistry
from botafuturo.adapters.paper.broker import PaperBrokerAdapter
from botafuturo.config.settings import Settings
from botafuturo.domain.models import Trade
from botafuturo.domain.risk.manager import RiskManager
from botafuturo.domain.session import TradingSession
from botafuturo.domain.strategy.ma_crossover import MovingAverageCrossoverStrategy
from botafuturo.ports.market_data import MarketDataPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WiredSession:
    """The composition root's output: a ready-to-run session plus its journal."""

    session: TradingSession
    trade_log: JsonlTradeLog
    registry: SecretRegistry


def _trade_to_record(trade: Trade) -> Mapping[str, Any]:
    """Flatten a `Trade` into a plain mapping, as `TradeLogPort.append` expects."""
    return {
        "order_id": trade.ack.order_id,
        "asset": trade.ack.request.asset,
        "direction": trade.ack.request.direction.value,
        "stake": trade.ack.request.stake,
        "opened_at": trade.ack.request.opened_at.isoformat(),
        "expiry_at": trade.ack.expiry_at.isoformat(),
        "entry_price": trade.ack.entry_price,
        "expiry_price": trade.expiry_price,
        "outcome": trade.outcome.value,
        "pnl": trade.pnl,
        "balance_after": trade.balance_after,
        "ts": trade.ack.expiry_at.isoformat(),
    }


def _journal_path(journal_dir: Union[str, Path], for_date: date) -> Path:
    return Path(journal_dir) / f"{for_date.isoformat()}.jsonl"


def build_paper_trading_session(
    settings: Settings,
    market_data: MarketDataPort,
    asset: str,
    journal_dir: Union[str, Path],
    *,
    today: Optional[date] = None,
) -> WiredSession:
    """Wire a full paper-trading `TradingSession` from `settings`.

    `market_data` is accepted (and type-checked structurally against
    `MarketDataPort`) but not constructed or stored here -- the caller (see
    `cli/run.py`) owns driving it through the session. Passing it into this
    function keeps the composition root's signature honest about what a
    full "session" needs, even though v1's wiring itself has no use for it
    yet (a future warm-start via `market_data.history(...)` could live here
    without changing this function's public shape).

    Journal records are written to `{journal_dir}/{today:%Y-%m-%d}.jsonl`
    (`today` defaults to the real current date; tests pass it explicitly for
    determinism).
    """
    registry = SecretRegistry()
    configure(registry)
    registry.register(settings.exnova_email.get_secret_value())
    registry.register(settings.exnova_password.get_secret_value())

    strategy = MovingAverageCrossoverStrategy(
        fast_period=settings.sma_fast_period,
        slow_period=settings.sma_slow_period,
    )
    risk_manager = RiskManager(
        day_start_balance=settings.starting_balance,
        max_daily_loss_pct=settings.max_daily_loss_pct,
        max_consecutive_losses=settings.max_consecutive_losses,
    )
    broker = PaperBrokerAdapter(starting_balance=settings.starting_balance)

    journal_date = today if today is not None else date.today()
    trade_log = JsonlTradeLog(_journal_path(journal_dir, journal_date), registry)

    def log_trade(trade: Trade) -> None:
        trade_log.append(_trade_to_record(trade))
        logger.info(
            "trade settled asset=%s outcome=%s pnl=%s balance_after=%s",
            trade.ack.request.asset,
            trade.outcome.value,
            trade.pnl,
            trade.balance_after,
        )

    session = TradingSession(
        asset=asset,
        strategy=strategy,
        risk_manager=risk_manager,
        stake=settings.stake_amount,
        expiry_s=settings.default_expiry_s,
        payout_rate=settings.payout_rate,
        open_position=broker.place,
        get_balance=broker.balance,
        settle_position=broker.settle,
        log_trade=log_trade,
    )

    return WiredSession(session=session, trade_log=trade_log, registry=registry)


def open_journal_for_report(journal_dir: Union[str, Path], for_date: date) -> JsonlTradeLog:
    """Open the journal file for `for_date` under `journal_dir`, for reading.

    Used by the `report` CLI command so `cli/main.py` never has to import
    `adapters/logging/` itself -- adapter construction stays confined to
    this composition root. No credential registration is needed here since
    this path only reads an existing journal, it never appends to one.
    """
    return JsonlTradeLog(_journal_path(journal_dir, for_date), SecretRegistry())
