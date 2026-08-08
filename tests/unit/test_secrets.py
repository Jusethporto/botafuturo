"""Tests for config/secrets.py — SecretProvider, the single chokepoint for
reading credential values from the environment or the OS keyring.
"""
from __future__ import annotations

import sys
import types

import pytest

from botafuturo.adapters.logging.redaction import SecretRegistry
from botafuturo.config.secrets import MissingCredential, SecretProvider


def test_get_reads_from_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTAFUTURO_TEST_SECRET", "s3cr3t-value")
    provider = SecretProvider()

    assert provider.get("BOTAFUTURO_TEST_SECRET") == "s3cr3t-value"


def test_get_raises_missing_credential_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BOTAFUTURO_TEST_SECRET_MISSING", raising=False)
    monkeypatch.setitem(sys.modules, "keyring", None)
    provider = SecretProvider()

    with pytest.raises(MissingCredential) as exc_info:
        provider.get("BOTAFUTURO_TEST_SECRET_MISSING")

    assert "BOTAFUTURO_TEST_SECRET_MISSING" in str(exc_info.value)


def test_get_falls_back_to_keyring_when_env_var_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BOTAFUTURO_TEST_KEYRING_SECRET", raising=False)

    fake_keyring = types.ModuleType("keyring")
    calls = []

    def fake_get_password(service: str, key: str) -> str:
        calls.append((service, key))
        return "keyring-value"

    fake_keyring.get_password = fake_get_password  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "keyring", fake_keyring)

    provider = SecretProvider()
    result = provider.get("BOTAFUTURO_TEST_KEYRING_SECRET")

    assert result == "keyring-value"
    assert calls == [("botafuturo", "BOTAFUTURO_TEST_KEYRING_SECRET")]


def test_get_treats_missing_keyring_package_as_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BOTAFUTURO_TEST_NO_KEYRING", raising=False)
    monkeypatch.setitem(sys.modules, "keyring", None)  # simulates ImportError

    provider = SecretProvider()
    with pytest.raises(MissingCredential):
        provider.get("BOTAFUTURO_TEST_NO_KEYRING")


def test_get_treats_keyring_error_as_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BOTAFUTURO_TEST_KEYRING_ERROR", raising=False)

    fake_keyring = types.ModuleType("keyring")

    def raising_get_password(service: str, key: str) -> str:
        raise RuntimeError("keyring backend unavailable")

    fake_keyring.get_password = raising_get_password  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "keyring", fake_keyring)

    provider = SecretProvider()
    with pytest.raises(MissingCredential):
        provider.get("BOTAFUTURO_TEST_KEYRING_ERROR")


def test_environment_variable_takes_priority_over_keyring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOTAFUTURO_TEST_PRIORITY", "from-env")

    fake_keyring = types.ModuleType("keyring")
    fake_keyring.get_password = lambda service, key: "from-keyring"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "keyring", fake_keyring)

    provider = SecretProvider()
    assert provider.get("BOTAFUTURO_TEST_PRIORITY") == "from-env"


def test_get_registers_retrieved_value_into_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOTAFUTURO_TEST_REGISTRY_SECRET", "register-me")
    registry = SecretRegistry()
    provider = SecretProvider()

    value = provider.get("BOTAFUTURO_TEST_REGISTRY_SECRET", registry=registry)

    assert value == "register-me"
    assert "register-me" in registry.values


def test_get_without_registry_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTAFUTURO_TEST_NO_REGISTRY", "value")
    provider = SecretProvider()

    assert provider.get("BOTAFUTURO_TEST_NO_REGISTRY") == "value"
