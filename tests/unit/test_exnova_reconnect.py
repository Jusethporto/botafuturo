"""Unit tests for `adapters/exnova/reconnect.py` -- pure exponential
backoff-with-full-jitter helper, no I/O.

Formula under test: `delay = random(0, min(cap, base * 2**attempt))`. Since
the delay is randomized, these tests assert BOUNDS and monotonicity of the
computed upper bound rather than exact values, except where a seeded
`random.Random` or a stub RNG makes an exact value legitimate to assert.
"""
from __future__ import annotations

import random

import pytest

from botafuturo.adapters.exnova.reconnect import backoff_delay


class _StubRng:
    """Minimal stand-in for `random.Random` that always returns the upper
    bound passed to `uniform`, so the exact backoff formula (the cap
    computation) can be asserted deterministically without depending on any
    particular PRNG's seeded output sequence."""

    def uniform(self, a: float, b: float) -> float:
        assert a == 0.0
        return b


def test_attempt_zero_upper_bound_equals_base() -> None:
    delay = backoff_delay(0, rng=_StubRng())
    assert delay == 1.0


def test_upper_bound_doubles_per_attempt_until_cap() -> None:
    assert backoff_delay(1, rng=_StubRng()) == 2.0
    assert backoff_delay(2, rng=_StubRng()) == 4.0
    assert backoff_delay(3, rng=_StubRng()) == 8.0
    assert backoff_delay(4, rng=_StubRng()) == 16.0
    assert backoff_delay(5, rng=_StubRng()) == 32.0


def test_upper_bound_is_capped_at_60_seconds_by_default() -> None:
    assert backoff_delay(6, rng=_StubRng()) == 60.0
    assert backoff_delay(20, rng=_StubRng()) == 60.0


def test_delay_is_never_negative_and_never_exceeds_the_cap() -> None:
    rng = random.Random(1234)
    for attempt in range(10):
        delay = backoff_delay(attempt, rng=rng)
        assert 0.0 <= delay <= 60.0


def test_delay_is_deterministic_given_the_same_seeded_rng_state() -> None:
    delay_a = backoff_delay(3, rng=random.Random(42))
    delay_b = backoff_delay(3, rng=random.Random(42))
    assert delay_a == delay_b


def test_custom_base_and_cap_are_respected() -> None:
    assert backoff_delay(0, base=2.0, cap=10.0, rng=_StubRng()) == 2.0
    assert backoff_delay(10, base=2.0, cap=10.0, rng=_StubRng()) == 10.0


def test_negative_attempt_raises_value_error() -> None:
    with pytest.raises(ValueError):
        backoff_delay(-1)


def test_omitting_rng_still_returns_a_value_in_bounds() -> None:
    delay = backoff_delay(2)
    assert 0.0 <= delay <= 4.0
