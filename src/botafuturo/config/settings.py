"""Application settings, loaded from environment variables and/or a `.env`
file via `pydantic-settings`.

Env var mapping is pydantic-settings' default: case-insensitive, field name
uppercased 1:1 (no prefix), so `exnova_email`/`exnova_password` map to the
`EXNOVA_EMAIL`/`EXNOVA_PASSWORD` variables already declared in `.env.example`
(created in PR1) without any extra configuration.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from botafuturo.config import defaults


class Settings(BaseSettings):
    """Runtime configuration: broker credentials (required, secret) plus
    risk/stake/strategy parameters (optional, defaulting to
    `config/defaults.py` values, overridable via env vars/.env).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    exnova_email: SecretStr
    exnova_password: SecretStr

    starting_balance: Decimal = defaults.STARTING_BALANCE
    payout_rate: Decimal = defaults.PAYOUT_RATE
    stake_amount: Decimal = defaults.STAKE_AMOUNT
    max_daily_loss_pct: Decimal = defaults.MAX_DAILY_LOSS_PCT
    max_consecutive_losses: int = defaults.MAX_CONSECUTIVE_LOSSES
    default_expiry_s: int = defaults.DEFAULT_EXPIRY_S
    sma_fast_period: int = defaults.SMA_FAST_PERIOD
    sma_slow_period: int = defaults.SMA_SLOW_PERIOD
