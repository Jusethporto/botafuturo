"""Architecture test: `BrokerMode` must have exactly one member (`PAPER`).

v1 ships paper-trading only -- `BrokerMode` exists so a future live-trading
mode is an explicit, additive, deliberately-reviewed change (see
`ports/broker.py`'s module docstring), never a silent side effect of some
unrelated PR. Adding a second member should force this assertion to be
updated on purpose, not slip in unnoticed.
"""
from __future__ import annotations

from botafuturo.ports.broker import BrokerMode


def test_broker_mode_has_exactly_one_member() -> None:
    members = list(BrokerMode)

    assert len(members) == 1
    assert members[0] is BrokerMode.PAPER
    assert members[0].value == "paper"
