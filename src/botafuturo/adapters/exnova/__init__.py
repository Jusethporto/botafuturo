"""Exnova adapters.

The validation spike (`docs/spike-report.md`) captured real protocol
details from the Exnova demo account, unblocking Phase 8: a real,
read-only `MarketDataPort` implementation (`market_data.py`, backed by
`session_auth.py` + `ws_client.py` + `mapping.py` + `reconnect.py`) now
lives in this package, streaming REAL live prices into the existing
paper-trading simulation.

A `BrokerPort` implementation (real order placement/settlement) is
deliberately NOT part of this package -- v1 ships paper-trading only (see
`tests/architecture/test_no_order_submission_surface.py` and
`test_only_paper_broker_implementation.py`, which this package must keep
passing). That remains a separate, deliberately scoped future change.
"""
