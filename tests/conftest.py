"""Root pytest configuration and shared fixtures."""
from __future__ import annotations

import logging

import pytest


@pytest.fixture(autouse=True)
def _reset_root_logger():
    """Snapshot/restore the stdlib root logger around every test.

    `botafuturo.adapters.logging.logging_setup.configure()` mutates GLOBAL,
    process-wide state (the root logger's filters/handlers) and is
    deliberately idempotent -- a second call with a *different*
    `SecretRegistry` is a silent no-op, by design (see its docstring).
    Multiple independent test modules call `configure()` (e.g.
    `test_logging_setup.py` directly, and `cli/wire.py`'s
    `build_paper_trading_session` indirectly via `tests/unit/test_cli_wire.py`
    and `tests/e2e/test_offline_session.py`). Without resetting root-logger
    state between tests, whichever test happens to run first "wins" the
    registry binding for the rest of the process, and later tests silently
    fail to see their own registered secrets redacted. This mirrors the
    fixture `test_logging_setup.py` already used locally, hoisted here so
    every test gets the same isolation regardless of file/run order.
    """
    root = logging.getLogger()
    original_filters = list(root.filters)
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    root.filters = original_filters
    root.handlers = original_handlers
    root.setLevel(original_level)
