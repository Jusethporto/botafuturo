"""Pure functions mapping raw Exnova WS message dicts to domain objects.

No I/O, no WebSocket/HTTP dependency -- these functions take a plain
`dict`/`Mapping` (already JSON-decoded) and return a domain object or raise
`MappingError`. `ws_client.py`/`market_data.py` are the only callers.

`active_id`<->symbol resolution: the wire protocol only carries a numeric
`active_id` (e.g. `86`), never a symbol string like `"EURUSD-OTC"`. Resolving
that mapping table was flagged in `docs/spike-report.md`'s "Open items" as
needing its own follow-up capture -- it is intentionally NOT solved here.
Instead, `to_candle` takes the target `asset` symbol as a caller-supplied
parameter and echoes it straight into `Candle.asset`; the caller (see
`market_data.py::ExnovaMarketDataAdapter`) is constructed with an externally
chosen `(asset_symbol, active_id)` pair, so this module never needs to look
one up itself.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from botafuturo.domain.models import Candle

_CANDLE_GENERATED = "candle-generated"

#: Fields required inside a `candle-generated` push's `msg` body.
_REQUIRED_CANDLE_FIELDS = ("from", "open", "close", "min", "max", "volume", "size")


class MappingError(Exception):
    """Raised when a raw WS message does not match the expected shape for
    the mapping function being called."""


def _to_decimal(value: Any) -> Decimal:
    # Values arrive as JSON floats (e.g. 0.984425). Convert via `str()`
    # first, never `Decimal(float)` directly, to avoid binary
    # floating-point rounding error leaking into a domain `Decimal` field --
    # see domain/models.py's module docstring on why floats are never used
    # for value-bearing fields in this codebase.
    return Decimal(str(value))


def to_candle(raw_msg: Mapping[str, Any], asset: str) -> Candle:
    """Map one `candle-generated` WS push to a domain `Candle`.

    `raw_msg` is the FULL push envelope (`{"name": ..., "msg": {...}}`), as
    received from `ws_client.py`, not just the inner body.

    A `candle-generated` push's `size` field is itself the candle's
    duration in seconds (e.g. `1` for 1-second candles) and the observed
    push cadence during the validation spike matched that duration exactly
    (~1 msg/sec at `size:1`) -- so, for v1, every received push is treated
    as already representing one CLOSED bar for that timeframe; there is no
    separate "is this candle closed yet" flag in the observed payload to
    check (see `docs/spike-report.md`).

    Raises:
        MappingError: if `raw_msg` is not a `candle-generated` push, or is
            missing an expected field.
    """
    if raw_msg.get("name") != _CANDLE_GENERATED:
        raise MappingError(
            f"expected a {_CANDLE_GENERATED!r} push, got name={raw_msg.get('name')!r}: "
            f"{raw_msg!r}"
        )

    body = raw_msg.get("msg")
    if not isinstance(body, Mapping):
        raise MappingError(
            f"malformed {_CANDLE_GENERATED!r} push, missing/invalid 'msg' body: {raw_msg!r}"
        )

    missing = [field for field in _REQUIRED_CANDLE_FIELDS if field not in body]
    if missing:
        raise MappingError(
            f"malformed {_CANDLE_GENERATED!r} push, missing field(s) {missing}: {raw_msg!r}"
        )

    open_time = datetime.fromtimestamp(body["from"], tz=timezone.utc)
    return Candle(
        asset=asset,
        open_time=open_time,
        open=_to_decimal(body["open"]),
        high=_to_decimal(body["max"]),
        low=_to_decimal(body["min"]),
        close=_to_decimal(body["close"]),
        volume=_to_decimal(body["volume"]),
        timeframe_s=int(body["size"]),
    )
