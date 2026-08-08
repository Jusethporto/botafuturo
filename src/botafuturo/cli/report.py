"""Journal summarization: aggregates a `TradeLogPort`'s history into simple
CLI-reportable stats.

Design choices, documented here since they are judgment calls rather than
derived facts:

  - `win_rate` is `wins / (wins + losses)`, deliberately EXCLUDING ties from
    the denominator. A tie is neither a win nor a loss (the stake is simply
    refunded), so folding it into the rate would understate performance for
    no analytical benefit.
  - When there are zero decisive (win or loss) trades -- including the
    zero-trades case and the all-ties case -- `win_rate` is `None` rather
    than `Decimal("0")`. A literal 0% win rate and "no data yet to judge"
    are different facts a caller should be able to tell apart; collapsing
    them to the same value would be misleading.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from botafuturo.ports.trade_log import TradeLogPort


@dataclass(frozen=True)
class TradeSummary:
    """Aggregate stats over every record in a trade journal."""

    trade_count: int
    win_count: int
    loss_count: int
    tie_count: int
    win_rate: Optional[Decimal]
    net_pnl: Decimal


def summarize(trade_log: TradeLogPort) -> TradeSummary:
    """Read every record from `trade_log` and aggregate it into a `TradeSummary`."""
    trade_count = 0
    win_count = 0
    loss_count = 0
    tie_count = 0
    net_pnl = Decimal("0")

    for record in trade_log.read():
        trade_count += 1
        outcome = record.get("outcome")
        if outcome == "win":
            win_count += 1
        elif outcome == "loss":
            loss_count += 1
        elif outcome == "tie":
            tie_count += 1

        pnl = record.get("pnl")
        if pnl is not None:
            net_pnl += Decimal(str(pnl))

    decisive = win_count + loss_count
    win_rate = (Decimal(win_count) / Decimal(decisive)) if decisive > 0 else None

    return TradeSummary(
        trade_count=trade_count,
        win_count=win_count,
        loss_count=loss_count,
        tie_count=tie_count,
        win_rate=win_rate,
        net_pnl=net_pnl,
    )


def print_summary(summary: TradeSummary) -> None:
    """Format `summary` as human-readable text and print it to stdout."""
    win_rate_text = "N/A" if summary.win_rate is None else f"{summary.win_rate:.2%}"
    print("Trade summary")
    print(f"  Trades:   {summary.trade_count}")
    print(f"  Wins:     {summary.win_count}")
    print(f"  Losses:   {summary.loss_count}")
    print(f"  Ties:     {summary.tie_count}")
    print(f"  Win rate: {win_rate_text}")
    print(f"  Net P&L:  {summary.net_pnl}")
