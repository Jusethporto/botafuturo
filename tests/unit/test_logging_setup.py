"""Unit tests for `configure()`: wiring `RedactingFilter` onto the root
logger and its handler.

Idempotency matters here: application code (and tests) may call `configure`
more than once without ending up with duplicated filters or handlers
double-emitting every log line.
"""
from __future__ import annotations

import logging

import pytest

from botafuturo.adapters.logging.logging_setup import configure
from botafuturo.adapters.logging.redaction import RedactingFilter, SecretRegistry

_SECRET = "s3kr1t-configure-value"


@pytest.fixture(autouse=True)
def _reset_root_logger():
    root = logging.getLogger()
    original_filters = list(root.filters)
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    root.filters = original_filters
    root.handlers = original_handlers
    root.setLevel(original_level)


def test_configure_is_idempotent_across_repeated_calls() -> None:
    registry = SecretRegistry()

    configure(registry)
    configure(registry)

    root = logging.getLogger()
    redacting_filters = [f for f in root.filters if isinstance(f, RedactingFilter)]
    assert len(redacting_filters) == 1

    our_handlers = [h for h in root.handlers if h.name == "botafuturo-redacting-handler"]
    assert len(our_handlers) == 1
    assert len([f for f in our_handlers[0].filters if isinstance(f, RedactingFilter)]) == 1


def test_configure_redacts_messages_logged_via_named_logger(capsys) -> None:
    registry = SecretRegistry()
    registry.register(_SECRET)
    configure(registry)

    logger = logging.getLogger("botafuturo.test.configure")
    logger.info("token is %s", _SECRET)

    captured = capsys.readouterr()
    assert _SECRET not in captured.err
    assert "***REDACTED***" in captured.err
