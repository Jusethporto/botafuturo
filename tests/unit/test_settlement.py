"""Unit tests for `resolve_outcome`: binary-option settlement logic.

Covers all 6 (direction x outcome) combinations exhaustively, per spec.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from botafuturo.domain.models import Direction, Outcome
from botafuturo.domain.settlement import resolve_outcome


class TestCallDirection:
    def test_call_wins_when_price_rises(self) -> None:
        result = resolve_outcome(Direction.CALL, Decimal("1.1000"), Decimal("1.1050"))
        assert result is Outcome.WIN

    def test_call_loses_when_price_falls(self) -> None:
        result = resolve_outcome(Direction.CALL, Decimal("1.1000"), Decimal("1.0950"))
        assert result is Outcome.LOSS

    def test_call_ties_when_price_unchanged(self) -> None:
        result = resolve_outcome(Direction.CALL, Decimal("1.1000"), Decimal("1.1000"))
        assert result is Outcome.TIE


class TestPutDirection:
    def test_put_wins_when_price_falls(self) -> None:
        result = resolve_outcome(Direction.PUT, Decimal("1.1000"), Decimal("1.0950"))
        assert result is Outcome.WIN

    def test_put_loses_when_price_rises(self) -> None:
        result = resolve_outcome(Direction.PUT, Decimal("1.1000"), Decimal("1.1050"))
        assert result is Outcome.LOSS

    def test_put_ties_when_price_unchanged(self) -> None:
        result = resolve_outcome(Direction.PUT, Decimal("1.1000"), Decimal("1.1000"))
        assert result is Outcome.TIE


@pytest.mark.parametrize(
    ("direction", "entry", "expiry", "expected"),
    [
        (Direction.CALL, Decimal("100"), Decimal("101"), Outcome.WIN),
        (Direction.CALL, Decimal("100"), Decimal("99"), Outcome.LOSS),
        (Direction.CALL, Decimal("100"), Decimal("100"), Outcome.TIE),
        (Direction.PUT, Decimal("100"), Decimal("99"), Outcome.WIN),
        (Direction.PUT, Decimal("100"), Decimal("101"), Outcome.LOSS),
        (Direction.PUT, Decimal("100"), Decimal("100"), Outcome.TIE),
    ],
)
def test_all_six_combinations(
    direction: Direction, entry: Decimal, expiry: Decimal, expected: Outcome
) -> None:
    assert resolve_outcome(direction, entry, expiry) is expected
