"""Unit tests for `Balance`: in-memory balance ledger for paper trading."""
from __future__ import annotations

from decimal import Decimal

import pytest

from botafuturo.adapters.paper.balance import Balance, InsufficientFunds


def test_get_returns_starting_balance() -> None:
    balance = Balance(Decimal("1000"))
    assert balance.get() == Decimal("1000")


def test_debit_reduces_balance() -> None:
    balance = Balance(Decimal("1000"))
    balance.debit(Decimal("100"))
    assert balance.get() == Decimal("900")


def test_credit_increases_balance() -> None:
    balance = Balance(Decimal("1000"))
    balance.credit(Decimal("50"))
    assert balance.get() == Decimal("1050")


def test_debit_exact_balance_is_allowed() -> None:
    balance = Balance(Decimal("10"))
    balance.debit(Decimal("10"))
    assert balance.get() == Decimal("0")


def test_debit_raises_when_it_would_go_negative() -> None:
    balance = Balance(Decimal("10"))
    with pytest.raises(InsufficientFunds):
        balance.debit(Decimal("10.01"))
    assert balance.get() == Decimal("10")
