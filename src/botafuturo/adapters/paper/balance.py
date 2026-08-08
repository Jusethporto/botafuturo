"""`Balance`: a simple in-memory Decimal ledger for paper trading."""
from __future__ import annotations

from decimal import Decimal


class InsufficientFunds(Exception):
    """Raised by `Balance.debit` when the debit would drive the balance negative."""


class Balance:
    """Tracks a single `Decimal` amount, in memory, with debit/credit ops."""

    def __init__(self, starting_balance: Decimal) -> None:
        self._amount = starting_balance

    def get(self) -> Decimal:
        """Return the current balance."""
        return self._amount

    def debit(self, amount: Decimal) -> None:
        """Subtract `amount` from the balance.

        Raises:
            InsufficientFunds: if `amount` exceeds the current balance
                (i.e. the debit would drive the balance negative).
        """
        if amount > self._amount:
            raise InsufficientFunds(
                f"cannot debit {amount} from balance {self._amount}"
            )
        self._amount -= amount

    def credit(self, amount: Decimal) -> None:
        """Add `amount` to the balance."""
        self._amount += amount
