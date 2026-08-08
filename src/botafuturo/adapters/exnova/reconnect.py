"""Reconnect backoff: exponential backoff with full jitter.

Pure, no I/O -- `backoff_delay(attempt)` is independently unit-testable
without a real clock or a real WebSocket connection. Formula (per the
design's documented reconnect/backoff strategy):

    delay = random(0, min(60, 1 * 2**attempt))

i.e. "full jitter" exponential backoff: the delay is a uniformly random
value between 0 and the exponential cap (not the cap itself), to avoid a
thundering herd of reconnects all firing at the same instant when many
clients drop together.
"""
from __future__ import annotations

import random
from typing import Optional

#: Default base delay (seconds) for `attempt=0`.
DEFAULT_BASE_S = 1.0
#: Default maximum delay (seconds), regardless of how many attempts have
#: elapsed.
DEFAULT_CAP_S = 60.0


def backoff_delay(
    attempt: int,
    *,
    base: float = DEFAULT_BASE_S,
    cap: float = DEFAULT_CAP_S,
    rng: Optional[random.Random] = None,
) -> float:
    """Return the delay (seconds) to wait before reconnect attempt `attempt`.

    `attempt` is 0-indexed: the first retry after a connection drop is
    `attempt=0`, the second is `attempt=1`, and so on -- each attempt
    doubles the exponential upper bound until it saturates at `cap`.

    `rng` is injectable for deterministic tests (pass a seeded
    `random.Random` instance, or any object exposing a compatible
    `uniform(a, b)` method); when omitted, a fresh `random.Random()` is
    used per call so this stays pure with respect to any shared,
    test-polluting module-level PRNG state.
    """
    if attempt < 0:
        raise ValueError(f"attempt must be >= 0, got {attempt}")
    if base <= 0:
        raise ValueError(f"base must be > 0, got {base}")
    if cap <= 0:
        raise ValueError(f"cap must be > 0, got {cap}")

    upper = min(cap, base * (2**attempt))
    generator = rng if rng is not None else random.Random()
    return generator.uniform(0.0, upper)
