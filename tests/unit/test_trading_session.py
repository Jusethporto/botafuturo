"""Unit tests for `TradingSession`, the pure orchestration core.

`TradingSession` has no real adapters yet (those land in PR3) -- it is
wired here against small inline fakes/stubs that satisfy the minimal
duck-typed shapes it depends on (a strategy, a risk manager, a
broker-like `open_position` callable, a `get_balance` callable, and a
`log_trade` callable).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, List, Mapping, Optional

import pytest

from botafuturo.domain.models import (
    Candle,
    Direction,
    OrderAck,
    OrderRequest,
    Quote,
    Signal,
    Trade,
)
from botafuturo.domain.pnl import pnl_for
from botafuturo.domain.risk.manager import RiskManager
from botafuturo.domain.session import TradingSession
from botafuturo.domain.settlement import resolve_outcome

_START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _candle(open_time: datetime, close: str, asset: str = "EURUSD") -> Candle:
    return Candle(
        asset=asset,
        open_time=open_time,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("100"),
        timeframe_s=60,
    )


class _ScriptedStrategy:
    """Emits a scripted sequence of signals, one per `on_candle` call."""

    name = "scripted"
    params: Mapping[str, Any] = {}

    def __init__(self, script: List[Optional[Signal]]) -> None:
        self._script = list(script)
        self._index = 0
        self.reset_calls = 0

    def warmup_bars(self) -> int:
        return 0

    def on_candle(self, candle: Candle) -> Optional[Signal]:
        if self._index >= len(self._script):
            return None
        signal = self._script[self._index]
        self._index += 1
        return signal


class _FakeBroker:
    """Records every fill request and returns a deterministic ack.

    `settle_position` mirrors the real `BrokerPort.settle` contract
    (resolve outcome + pnl from the injected `get_balance` callable) so
    these behavioral tests keep exercising `TradingSession` against a
    broker-shaped `settle_position` collaborator, exactly like the real
    wiring in `cli/wire.py`.
    """

    def __init__(self, get_balance: Any) -> None:
        self.requests: List[OrderRequest] = []
        self._next_id = 1
        self._get_balance = get_balance

    def open_position(self, request: OrderRequest) -> OrderAck:
        self.requests.append(request)
        ack = OrderAck(
            order_id=f"order-{self._next_id}",
            request=request,
            expiry_at=request.opened_at + timedelta(seconds=request.expiry_s),
            entry_price=Decimal("100"),
        )
        self._next_id += 1
        return ack

    def settle_position(self, ack: OrderAck, quote: Quote) -> Trade:
        outcome = resolve_outcome(ack.request.direction, ack.entry_price, quote.price)
        pnl = pnl_for(outcome, ack.request.stake, ack.request.payout_rate)
        return Trade(
            ack=ack,
            expiry_price=quote.price,
            outcome=outcome,
            pnl=pnl,
            balance_after=self._get_balance() + pnl,
        )


class _FakeTradeLog:
    def __init__(self) -> None:
        self.trades: List[Trade] = []

    def log_trade(self, trade: Trade) -> None:
        self.trades.append(trade)


def _signal(asset: str, direction: Direction, ts: datetime) -> Signal:
    return Signal(asset=asset, direction=direction, emitted_at=ts, strategy_name="scripted")


def _build_session(
    script: List[Optional[Signal]],
    risk_manager: Optional[RiskManager] = None,
    balance: str = "1000",
    expiry_s: int = 60,
):
    strategy = _ScriptedStrategy(script)
    broker = _FakeBroker(get_balance=lambda: Decimal(balance))
    trade_log = _FakeTradeLog()
    manager = risk_manager or RiskManager(day_start_balance=Decimal(balance))
    session = TradingSession(
        asset="EURUSD",
        strategy=strategy,
        risk_manager=manager,
        stake=Decimal("10"),
        expiry_s=expiry_s,
        payout_rate=Decimal("0.85"),
        open_position=broker.open_position,
        get_balance=lambda: Decimal(balance),
        settle_position=broker.settle_position,
        log_trade=trade_log.log_trade,
    )
    return session, strategy, broker, trade_log, manager


class TestOpensAndSettlesPosition:
    def test_opens_position_on_signal_and_settles_at_expiry(self) -> None:
        t0 = _START
        script = [_signal("EURUSD", Direction.CALL, t0), None]
        session, _strategy, broker, trade_log, _manager = _build_session(script)

        session.on_candle(_candle(t0, "100"))
        assert len(broker.requests) == 1
        assert broker.requests[0].direction is Direction.CALL
        assert trade_log.trades == []

        t1 = t0 + timedelta(seconds=60)
        session.on_candle(_candle(t1, "110"))
        assert len(trade_log.trades) == 1
        trade = trade_log.trades[0]
        assert trade.outcome.name == "WIN"
        assert trade.pnl == Decimal("8.50")


class TestSingleOpenPosition:
    def test_ignores_new_signal_while_position_open(self) -> None:
        t0 = _START
        t1 = t0 + timedelta(seconds=1)
        script = [
            _signal("EURUSD", Direction.CALL, t0),
            _signal("EURUSD", Direction.PUT, t1),
        ]
        # expiry_s large so the first position is still open at t1.
        session, _strategy, broker, _trade_log, _manager = _build_session(
            script, expiry_s=3600
        )

        session.on_candle(_candle(t0, "100"))
        assert len(broker.requests) == 1

        session.on_candle(_candle(t1, "101"))
        assert len(broker.requests) == 1  # second signal ignored: position open


class TestSingleInstrument:
    def test_raises_on_candle_for_different_asset(self) -> None:
        session, _strategy, _broker, _trade_log, _manager = _build_session([None])
        foreign_candle = _candle(_START, "100", asset="GBPUSD")
        with pytest.raises(ValueError):
            session.on_candle(foreign_candle)


class TestRiskManagerGating:
    def test_does_not_open_position_when_risk_manager_halted(self) -> None:
        manager = RiskManager(day_start_balance=Decimal("1000"))
        from botafuturo.domain.models import Direction as _D
        from botafuturo.domain.models import OrderAck as _Ack
        from botafuturo.domain.models import OrderRequest as _Req
        from botafuturo.domain.models import Outcome
        from botafuturo.domain.models import Trade as _Trade

        # Force a halt via a real large loss, using the public API.
        request = _Req(
            asset="EURUSD",
            direction=_D.CALL,
            stake=Decimal("10"),
            expiry_s=60,
            opened_at=_START,
            payout_rate=Decimal("0.85"),
        )
        ack = _Ack(order_id="x", request=request, expiry_at=_START, entry_price=Decimal("1"))
        halting_trade = _Trade(
            ack=ack,
            expiry_price=Decimal("1"),
            outcome=Outcome.LOSS,
            pnl=Decimal("-100"),
            balance_after=Decimal("900"),
        )
        manager.record(halting_trade)

        script = [_signal("EURUSD", Direction.CALL, _START)]
        session, _strategy, broker, _trade_log, _manager2 = _build_session(
            script, risk_manager=manager
        )

        session.on_candle(_candle(_START, "100"))
        assert broker.requests == []
