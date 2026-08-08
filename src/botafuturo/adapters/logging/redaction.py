"""Redaction chokepoint for logs, journals, and CLI output.

`SecretRegistry` + `redact_text` + `redact_mapping` are a SINGLE, testable
chokepoint that ALL log/journal/CLI output is meant to pass through, instead
of relying on scattered per-call-site scrubbing (which is easy to forget at
any one of many call sites). `RedactingFilter` wires this chokepoint into
Python's standard `logging` module via the standard `logging.Filter`
extension point.

Redaction catches two independent things:
  1. Explicitly-registered secret values (exact substring match), via
     `SecretRegistry`.
  2. Common secret-*shaped* substrings, via regex, even when NOT registered:
     `password=`/`password:`-style key-value pairs (also `token`, `ssid`,
     `session_id`, `api_key`, ...), `Bearer <token>` auth headers,
     JWT-shaped strings, and email addresses.
"""
from __future__ import annotations

import logging
import re
from typing import Any, FrozenSet, List, Mapping, Set

_REDACTED = "***REDACTED***"

# key=value / key: value secret-shaped pairs (password, token, ssid, ...).
_SECRET_KV = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|ssid|session[_-]?id)"
    r"(\s*[:=]\s*)(\S+)"
)
# `Bearer <token>` authorization headers.
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+(\S+)")
# JWT-shaped strings: three base64url segments separated by dots.
_JWT = re.compile(r"\b[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b")
# Email addresses.
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


class SecretRegistry:
    """Holds the set of known secret values that must be redacted."""

    def __init__(self) -> None:
        self._values: Set[str] = set()

    def register(self, value: str) -> None:
        """Record `value` as a secret to redact from all future output."""
        if value:
            self._values.add(value)

    @property
    def values(self) -> FrozenSet[str]:
        return frozenset(self._values)


def _redact_kv(match: "re.Match[str]") -> str:
    return f"{match.group(1)}{match.group(2)}{_REDACTED}"


def redact_text(text: str, registry: SecretRegistry) -> str:
    """Return `text` with every registered secret AND every secret-shaped
    pattern (password=, Bearer tokens, JWT-shaped strings, emails) replaced
    by `***REDACTED***`. Non-string input is returned unchanged.
    """
    if not isinstance(text, str):
        return text

    result = text
    for secret in registry.values:
        result = result.replace(secret, _REDACTED)

    result = _SECRET_KV.sub(_redact_kv, result)
    result = _BEARER_TOKEN.sub(f"Bearer {_REDACTED}", result)
    result = _JWT.sub(_REDACTED, result)
    result = _EMAIL.sub(_REDACTED, result)
    return result


def redact_mapping(data: Mapping[str, Any], registry: SecretRegistry) -> dict:
    """Recursively redact every string value in `data` (dict/list structure),
    leaving keys and non-string values untouched. Returns a NEW structure;
    never mutates `data`.
    """

    def _walk(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {key: _walk(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            walked: List[Any] = [_walk(item) for item in value]
            return type(value)(walked) if isinstance(value, tuple) else walked
        if isinstance(value, str):
            return redact_text(value, registry)
        return value

    return _walk(data)


class RedactingFilter(logging.Filter):
    """`logging.Filter` that redacts every emitted record (its message and
    its format args) through the redaction chokepoint before it reaches a
    handler/formatter. Installable on either a `Logger` or a `Handler` --
    `configure()` in `logging_setup.py` installs it on both, since a
    `Logger`-level filter only fires for records originated on that exact
    logger, while a `Handler`-level filter fires for every record that
    reaches it regardless of which logger produced it.
    """

    def __init__(self, registry: SecretRegistry) -> None:
        super().__init__()
        self._registry = registry

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact the FINAL, fully-substituted message (`record.getMessage()`
        # safely does `record.msg % record.args` using the ORIGINAL,
        # not-yet-redacted values) instead of redacting `record.msg` and
        # `record.args` independently. Redacting the raw, un-substituted
        # template on its own is unsafe: a template shaped like
        # `"password=%s"` has its OWN `%s` placeholder matched by the
        # secret-shaped key=value regex (`%s` satisfies `\S+`) and gets
        # rewritten to `"password=***REDACTED***"`, destroying the
        # placeholder while `record.args` still holds an argument -- so
        # stdlib's `record.msg % record.args` later raises
        # `TypeError: not all arguments converted during string formatting`
        # inside `Handler.emit()`, silently dropping the record.
        message = record.getMessage()
        record.msg = redact_text(message, self._registry)
        # The message is now fully substituted and already redacted; clear
        # `args` (not `()` -- `None` is the conventional "no args" sentinel,
        # and `record.getMessage()` treats both as falsy) so nothing
        # downstream re-attempts `%`-substitution into the redacted string.
        record.args = None
        return True
