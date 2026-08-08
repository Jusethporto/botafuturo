"""Settlement logic: resolves a closed binary-option trade's outcome."""
from __future__ import annotations

from decimal import Decimal

from botafuturo.domain.models import Direction, Outcome


def resolve_outcome(
    direction: Direction, entry_price: Decimal, expiry_price: Decimal
) -> Outcome:
    """Resolve the outcome of a trade given its direction and prices.

    CALL wins if the price rose (expiry > entry), loses if it fell, ties
    if unchanged. PUT is the mirror image.
    """
    if expiry_price == entry_price:
        return Outcome.TIE

    price_rose = expiry_price > entry_price
    if direction is Direction.CALL:
        return Outcome.WIN if price_rose else Outcome.LOSS
    return Outcome.LOSS if price_rose else Outcome.WIN
