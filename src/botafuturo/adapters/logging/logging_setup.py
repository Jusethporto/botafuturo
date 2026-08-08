"""Wires `RedactingFilter` onto the standard-library root logger.

`configure()` is the single place production code (and the CLI, in a later
PR) calls to guarantee every log record -- regardless of which module or
named logger emits it -- passes through the redaction chokepoint before it
reaches a handler/stream. It installs the filter on BOTH the root logger and
its handler: a `Logger`-level filter only applies to records originated
directly on that logger object (per the stdlib `Logger.handle` /
`Logger.filter` semantics), while a `Handler`-level filter applies to every
record that reaches that handler during propagation, regardless of which
named logger (e.g. `logging.getLogger(__name__)`) originated it. The
handler-level filter is what makes this an actual single chokepoint for
normal application logging.
"""
from __future__ import annotations

import logging

from botafuturo.adapters.logging.redaction import RedactingFilter, SecretRegistry

_HANDLER_NAME = "botafuturo-redacting-handler"
_FORMATTER = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")


def configure(registry: SecretRegistry, level: int = logging.INFO) -> None:
    """Install a `RedactingFilter(registry)` on the root logger and ensure a
    basic `StreamHandler` (also carrying the filter) exists. Idempotent:
    calling this more than once never double-installs the filter or
    duplicates the handler.
    """
    root = logging.getLogger()
    root.setLevel(level)

    if not any(isinstance(existing, RedactingFilter) for existing in root.filters):
        root.addFilter(RedactingFilter(registry))

    handler = next(
        (h for h in root.handlers if h.name == _HANDLER_NAME), None
    )
    if handler is None:
        handler = logging.StreamHandler()
        handler.name = _HANDLER_NAME
        handler.setFormatter(_FORMATTER)
        root.addHandler(handler)

    if not any(isinstance(existing, RedactingFilter) for existing in handler.filters):
        handler.addFilter(RedactingFilter(registry))
