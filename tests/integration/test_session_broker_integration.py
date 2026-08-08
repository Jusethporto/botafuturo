"""Integration test: `TradingSession` wired to a REAL `PaperBrokerAdapter`.

Regression coverage for the bug where `TradingSession._maybe_settle`
independently recomputed outcome/pnl instead of delegating to the broker's
`settle()`, so the broker's real balance ledger was only ever debited on
`place()` and never credited back on settlement (every trade -- WIN, LOSS,
or TIE -- permanently drained the stake). This test wires the session the
exact same way `cli/wire.py`'s `build_paper_trading_session` does
(`open_position=broker.place`, `get_balance=broker.balance`,
`settle_position=broker.settle`) and proves the broker's actual balance
ledger is correctly credited back on every settlement, not just debited on
every open.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, List, Mapping, Optional, Tuple

from botafuturo.adapters.paper.broker import PaperBrokerAdapter
from botafuturo.domain.models import Candle, Direction, Outcome, Signal, Trade
from botafuturo.domain.risk.manager import RiskManager
from botafuturo.domain.session import TradingSession

_ASSET = "EURUSD"
_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
_TIMEFRAME_S = 60
_STAKE = Decimal("100")
_PAYOUT_RATE = Decimal("0.85")
_STARTING_BALANCE = Decimal("1000")


def _candle(open_time: datetime, close: str) -> Candle:
    return Candle(
        asset=_ASSET,
        open_time=open_time,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("10"),
        timeframe_s=_TIMEFRAME_S,
    )


def _signal(direction: Direction, ts: datetime) -> Signal:
    return Signal(asset=_ASSET, direction=direction, emitted_at=ts, strategy_name="scripted")


class _ScriptedStrategy:
    """Emits a scripted sequence of signals, one per `on_candle` call."""

    name = "scripted"
    params: Mapping[str, Any] = {}

    def __init__(self, script: List[Optional[Signal]]) -> None:
        self._script = list(script)
        self._index = 0

    def warmup_bars(self) -> int:
        return 0

    def on_candle(self, candle: Candle) -> Optional[Signal]:
        if self._index >= len(self._script):
            return None
        signal = self._script[self._index]
        self._index += 1
        return signal


def test_real_broker_stake_is_credited_back_on_every_settlement() -> None:
    """A WIN, a LOSS, and a TIE round-trip through a REAL `PaperBrokerAdapter`.

    Candle sequence (entry price is always fixed at 100 by
    `PaperBrokerAdapter.place`):

    - candle0: signal CALL -> opens trade A.
    - candle1 (close=110, > 100): settles A as WIN, signal PUT -> opens B.
    - candle2 (close=110, > 100): settles B as LOSS (price rose but PUT
      needs it to fall), signal CALL -> opens C.
    - candle3 (close=100, == 100): settles C as TIE, no further signal.
    """
    broker = PaperBrokerAdapter(starting_balance=_STARTING_BALANCE)
    risk_manager = RiskManager(day_start_balance=_STARTING_BALANCE)

    script = [
        _signal(Direction.CALL, _START),
        _signal(Direction.PUT, _START + timedelta(seconds=_TIMEFRAME_S)),
        _signal(Direction.CALL, _START + timedelta(seconds=2 * _TIMEFRAME_S)),
        None,
    ]
    strategy = _ScriptedStrategy(script)

    balances_before_open: List[Decimal] = []

    def _open_position(request):
        balances_before_open.append(broker.balance())
        return broker.place(request)

    settled: List[Tuple[Trade, Decimal]] = []

    def _log_trade(trade: Trade) -> None:
        settled.append((trade, broker.balance()))

    session = TradingSession(
        asset=_ASSET,
        strategy=strategy,
        risk_manager=risk_manager,
        stake=_STAKE,
        expiry_s=_TIMEFRAME_S,
        payout_rate=_PAYOUT_RATE,
        open_position=_open_position,
        get_balance=broker.balance,
        settle_position=broker.settle,
        log_trade=_log_trade,
    )

    session.on_candle(_candle(_START, "100"))
    session.on_candle(_candle(_START + timedelta(seconds=_TIMEFRAME_S), "110"))
    session.on_candle(_candle(_START + timedelta(seconds=2 * _TIMEFRAME_S), "110"))
    session.on_candle(_candle(_START + timedelta(seconds=3 * _TIMEFRAME_S), "100"))

    assert len(settled) == 3
    outcomes = [trade.outcome for trade, _ in settled]
    assert outcomes == [Outcome.WIN, Outcome.LOSS, Outcome.TIE]

    # 1. The broker's real balance reflects starting balance plus the sum
    #    of every trade's pnl -- proving stake is credited back, not just
    #    debited.
    total_pnl = sum((trade.pnl for trade, _ in settled), Decimal("0"))
    assert broker.balance() == _STARTING_BALANCE + total_pnl
    assert broker.balance() == Decimal("985")

    # 2. Every recorded Trade.balance_after matches the broker's ACTUAL
    #    running balance at that point in time (not just internally
    #    consistent with a locally-recomputed formula).
    for trade, balance_snapshot in settled:
        assert trade.balance_after == balance_snapshot

    # 3. The WIN trade's balance change relative to the balance right
    #    before that trade was opened is exactly +stake*payout_rate.
    win_index = outcomes.index(Outcome.WIN)
    balance_before_win = balances_before_open[win_index]
    balance_after_win = settled[win_index][1]
    assert balance_after_win - balance_before_win == _STAKE * _PAYOUT_RATE
    assert balance_after_win - balance_before_win == Decimal("85")

    # Sanity: the LOSS trade fully forfeits the stake, the TIE trade is a
    # net-zero round trip.
    loss_index = outcomes.index(Outcome.LOSS)
    balance_before_loss = balances_before_open[loss_index]
    balance_after_loss = settled[loss_index][1]
    assert balance_after_loss - balance_before_loss == -_STAKE

    tie_index = outcomes.index(Outcome.TIE)
    balance_before_tie = balances_before_open[tie_index]
    balance_after_tie = settled[tie_index][1]
    assert balance_after_tie - balance_before_tie == Decimal("0")
