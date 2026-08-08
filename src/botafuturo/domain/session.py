"""`TradingSession`: pure orchestration of strategy, risk, and settlement.

This is intentionally decoupled from real adapters (the concrete Port
protocols land in PR3). Collaborators are injected as simple duck-typed
callables/objects so a future adapter wiring can plug in without changing
this module's public shape:

- `open_position(request: OrderRequest) -> OrderAck` -- broker-like fill.
- `get_balance() -> Decimal` -- current account balance.
- `settle_position(ack: OrderAck, expiry_quote: Quote) -> Trade` --
  broker-like settlement. `TradingSession` delegates outcome/pnl/balance
  computation entirely to this collaborator (it does not recompute them
  itself) so the broker's real ledger -- not a locally-recomputed
  duplicate -- is always the single source of truth for a `Trade`.
- `log_trade(trade: Trade) -> None` -- trade-log-like sink.

`TradingSession` is scoped to a single instrument (`asset`) and enforces
at most one open position at a time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Optional

from botafuturo.domain.models import Candle, OrderAck, OrderRequest, Quote, Signal, Trade
from botafuturo.domain.risk.manager import RiskManager
from botafuturo.domain.strategy.base import Strategy


@dataclass
class TradingSession:
    """Feeds candles through a strategy and manages the single open position."""

    asset: str
    strategy: Strategy
    risk_manager: RiskManager
    stake: Decimal
    expiry_s: int
    payout_rate: Decimal
    open_position: Callable[[OrderRequest], OrderAck]
    get_balance: Callable[[], Decimal]
    settle_position: Callable[[OrderAck, Quote], Trade]
    log_trade: Callable[[Trade], None]

    _open: Optional[OrderAck] = field(default=None, init=False, repr=False)

    def on_candle(self, candle: Candle) -> None:
        """Advance the session by one candle.

        Order of operations: settle any expired open position first (using
        this candle's close as the expiry price), then feed the candle to
        the strategy, then possibly open a new position.
        """
        if candle.asset != self.asset:
            raise ValueError(
                f"TradingSession for {self.asset!r} received a candle for "
                f"{candle.asset!r}; a session tracks exactly one instrument."
            )

        self._maybe_settle(candle)

        signal = self.strategy.on_candle(candle)

        if signal is not None and self._open is None:
            self._maybe_open(candle, signal)

    def _maybe_settle(self, candle: Candle) -> None:
        if self._open is None:
            return
        if candle.open_time < self._open.expiry_at:
            return

        expiry_quote = Quote(asset=candle.asset, ts=candle.open_time, price=candle.close)
        trade = self.settle_position(self._open, expiry_quote)

        self.risk_manager.record(trade)
        self.log_trade(trade)
        self._open = None

    def _maybe_open(self, candle: Candle, signal: Signal) -> None:
        current_balance = self.get_balance()
        allowed, _reason = self.risk_manager.can_open(self.stake, current_balance)
        if not allowed:
            return

        request = OrderRequest(
            asset=self.asset,
            direction=signal.direction,
            stake=self.stake,
            expiry_s=self.expiry_s,
            opened_at=candle.open_time,
            payout_rate=self.payout_rate,
        )
        self._open = self.open_position(request)
