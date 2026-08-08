"""Unit tests for the redaction chokepoint.

`SecretRegistry` + `redact_text` + `redact_mapping` + `RedactingFilter` are
meant to be the SINGLE place secrets get scrubbed from -- not scattered
per-call-site scrubbing. These tests prove both explicitly-registered secret
values AND common secret-shaped patterns (password=, Bearer tokens,
JWT-shaped strings, emails) get redacted, and that `RedactingFilter` actually
wires this chokepoint into Python's standard `logging` module end-to-end.
"""
from __future__ import annotations

import logging

from botafuturo.adapters.logging.redaction import (
    RedactingFilter,
    SecretRegistry,
    redact_mapping,
    redact_text,
)

_SECRET = "s3kr1t-token-value"
_REDACTED = "***REDACTED***"


def _registry_with(*secrets: str) -> SecretRegistry:
    registry = SecretRegistry()
    for secret in secrets:
        registry.register(secret)
    return registry


def test_redact_text_redacts_registered_secret_value() -> None:
    registry = _registry_with(_SECRET)
    text = f"connecting with token {_SECRET} now"

    result = redact_text(text, registry)

    assert _SECRET not in result
    assert _REDACTED in result


def test_secret_registry_values_exposes_registered_secrets() -> None:
    registry = _registry_with(_SECRET, "another-secret")

    assert registry.values == frozenset({_SECRET, "another-secret"})


def test_redact_text_redacts_password_key_value_pairs() -> None:
    registry = SecretRegistry()

    assert "hunter2" not in redact_text("password=hunter2", registry)
    assert "hunter2" not in redact_text("password: hunter2", registry)
    assert "hunter2" not in redact_text("PASSWORD=hunter2", registry)


def test_redact_text_redacts_bearer_token() -> None:
    registry = SecretRegistry()
    text = "Authorization: Bearer abc123.def456xyz"

    result = redact_text(text, registry)

    assert "abc123.def456xyz" not in result
    assert "Bearer" in result


def test_redact_text_redacts_jwt_shaped_string() -> None:
    registry = SecretRegistry()
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    )
    text = f"session token is {jwt}"

    result = redact_text(text, registry)

    assert jwt not in result
    assert _REDACTED in result


def test_redact_text_redacts_email_address() -> None:
    registry = SecretRegistry()
    text = "contact user@example.com for support"

    result = redact_text(text, registry)

    assert "user@example.com" not in result
    assert _REDACTED in result


def test_redact_text_redacts_session_and_ssid_key_value_pairs() -> None:
    registry = SecretRegistry()

    assert "abc999" not in redact_text("ssid=abc999", registry)
    assert "abc999" not in redact_text("session_id: abc999", registry)


def test_redact_text_leaves_unrelated_text_untouched() -> None:
    registry = SecretRegistry()
    text = "order filled at price 100.5 for asset EURUSD"

    result = redact_text(text, registry)

    assert result == text


def test_redact_mapping_redacts_nested_dicts_and_lists_without_mutating_input() -> None:
    registry = _registry_with(_SECRET)
    original = {
        "user": "alice",
        "credentials": {"password": _SECRET, "notes": ["fine", _SECRET]},
    }

    redacted = redact_mapping(original, registry)

    assert redacted["credentials"]["password"] == _REDACTED
    assert redacted["credentials"]["notes"] == ["fine", _REDACTED]
    assert original["credentials"]["password"] == _SECRET
    assert original["credentials"]["notes"][1] == _SECRET


def test_redact_mapping_leaves_non_string_values_untouched() -> None:
    registry = SecretRegistry()
    original = {"stake": 10, "active": True, "meta": None}

    redacted = redact_mapping(original, registry)

    assert redacted == original


def test_redacting_filter_redacts_through_real_logger(caplog) -> None:
    registry = _registry_with(_SECRET)
    logger = logging.getLogger("botafuturo.test.redaction")
    logger.addFilter(RedactingFilter(registry))
    try:
        with caplog.at_level(logging.INFO, logger="botafuturo.test.redaction"):
            logger.info("login used token %s", _SECRET)

        assert _SECRET not in caplog.text
        assert _REDACTED in caplog.text
    finally:
        logger.filters.clear()
