"""Single chokepoint for reading credential values.

`SecretProvider.get()` is the ONLY call site in this codebase allowed to
unwrap a raw credential from `os.environ` or from the OS `keyring` backend.
This is enforced by `tests/architecture/test_single_secret_unwrap.py`, which
AST-scans every other module under `src/botafuturo` for `os.environ`/
`os.getenv`/`keyring.get_password` calls. Any other code that needs a
credential must go through `SecretProvider` instead of reading it directly.
"""
from __future__ import annotations

import os
from typing import Optional

from botafuturo.adapters.logging.redaction import SecretRegistry

_KEYRING_SERVICE = "botafuturo"


class MissingCredential(Exception):
    """Raised when a required credential is not found in the environment or
    the OS keyring."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(
            f"Missing credential '{key}': not found in environment variables "
            f"or in the OS keyring (service '{_KEYRING_SERVICE}')."
        )


class SecretProvider:
    """Resolves a credential value from the environment, falling back to the
    OS keyring when the optional `keyring` package is installed.
    """

    def get(self, key: str, registry: Optional[SecretRegistry] = None) -> str:
        value = os.environ.get(key)

        if not value:
            value = self._from_keyring(key)

        if not value:
            raise MissingCredential(key)

        if registry is not None:
            registry.register(value)

        return value

    @staticmethod
    def _from_keyring(key: str) -> Optional[str]:
        try:
            import keyring
        except ImportError:
            return None

        try:
            return keyring.get_password(_KEYRING_SERVICE, key)
        except Exception:
            return None
