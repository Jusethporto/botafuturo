"""Tests for config/settings.py — Settings (pydantic-settings BaseSettings).

Tests use `monkeypatch.setenv`/`delenv` and pass `_env_file=None` at
instantiation to isolate them from any real `.env` file that may or may not
exist on disk, per pydantic-settings' documented per-instance source
override mechanism.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from botafuturo.config import defaults
from botafuturo.config.settings import Settings


@pytest.fixture()
def clean_credential_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure no leftover EXNOVA_*/STAKE_AMOUNT env vars leak between tests."""
    monkeypatch.delenv("EXNOVA_EMAIL", raising=False)
    monkeypatch.delenv("EXNOVA_PASSWORD", raising=False)
    monkeypatch.delenv("STAKE_AMOUNT", raising=False)


def test_settings_loads_credentials_from_environment_variables(
    clean_credential_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EXNOVA_EMAIL", "trader@example.com")
    monkeypatch.setenv("EXNOVA_PASSWORD", "hunter2")

    settings = Settings(_env_file=None)

    assert settings.exnova_email.get_secret_value() == "trader@example.com"
    assert settings.exnova_password.get_secret_value() == "hunter2"


def test_settings_missing_required_credentials_raises_validation_error(
    clean_credential_env: None,
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_non_secret_fields_default_to_config_defaults(
    clean_credential_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EXNOVA_EMAIL", "trader@example.com")
    monkeypatch.setenv("EXNOVA_PASSWORD", "hunter2")

    settings = Settings(_env_file=None)

    assert settings.starting_balance == defaults.STARTING_BALANCE
    assert settings.payout_rate == defaults.PAYOUT_RATE
    assert settings.stake_amount == defaults.STAKE_AMOUNT
    assert settings.max_daily_loss_pct == defaults.MAX_DAILY_LOSS_PCT
    assert settings.max_consecutive_losses == defaults.MAX_CONSECUTIVE_LOSSES
    assert settings.default_expiry_s == defaults.DEFAULT_EXPIRY_S
    assert settings.sma_fast_period == defaults.SMA_FAST_PERIOD
    assert settings.sma_slow_period == defaults.SMA_SLOW_PERIOD


def test_settings_non_secret_fields_overridable_via_env(
    clean_credential_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EXNOVA_EMAIL", "trader@example.com")
    monkeypatch.setenv("EXNOVA_PASSWORD", "hunter2")
    monkeypatch.setenv("STAKE_AMOUNT", "25.00")

    settings = Settings(_env_file=None)

    assert settings.stake_amount == Decimal("25.00")


def test_secret_str_fields_never_reveal_raw_value_in_repr_or_str(
    clean_credential_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EXNOVA_EMAIL", "trader@example.com")
    monkeypatch.setenv("EXNOVA_PASSWORD", "super-secret-password")

    settings = Settings(_env_file=None)

    assert "super-secret-password" not in repr(settings)
    assert "super-secret-password" not in str(settings)
    assert "trader@example.com" not in repr(settings)
    assert "trader@example.com" not in str(settings)
    assert repr(settings.exnova_password) == "SecretStr('**********')"
    assert str(settings.exnova_password) == "**********"
