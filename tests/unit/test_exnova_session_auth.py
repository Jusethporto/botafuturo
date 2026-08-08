"""Unit tests for `adapters/exnova/session_auth.py` -- the HTTP login call
(`POST /v2/login`). No real network I/O: `http_post` is injected as a fake
callable in every test.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pytest
from pydantic import SecretStr

from botafuturo.adapters.exnova.session_auth import LoginError, LoginResult, login
from botafuturo.adapters.logging.redaction import SecretRegistry

_EMAIL = SecretStr("trader@example.com")
_PASSWORD = SecretStr("s3cr3t-password")
_SSID = "abc123ssid"


@dataclass
class _FakeResponse:
    status_code: int
    _body: Mapping[str, Any]

    def json(self) -> Mapping[str, Any]:
        return self._body


def _success_body() -> Mapping[str, Any]:
    return {
        "code": "success",
        "company_id": 15,
        "created_at": 1780000000,
        "ssid": _SSID,
        "token": "sometoken",
        "user_id": 42,
    }


def test_login_sends_identifier_and_password_in_request_body() -> None:
    calls = []

    def fake_http_post(url: str, *, json: Mapping[str, Any]) -> _FakeResponse:
        calls.append((url, json))
        return _FakeResponse(status_code=200, _body=_success_body())

    login(_EMAIL, _PASSWORD, http_post=fake_http_post)

    assert len(calls) == 1
    url, body = calls[0]
    assert url.endswith("/v2/login")
    assert body == {"identifier": "trader@example.com", "password": "s3cr3t-password"}


def test_login_returns_ssid_as_secret_str_on_success() -> None:
    def fake_http_post(url: str, *, json: Mapping[str, Any]) -> _FakeResponse:
        return _FakeResponse(status_code=200, _body=_success_body())

    result = login(_EMAIL, _PASSWORD, http_post=fake_http_post)

    assert isinstance(result, LoginResult)
    assert isinstance(result.ssid, SecretStr)
    assert result.ssid.get_secret_value() == _SSID
    assert result.user_id == 42
    assert result.company_id == 15


def test_login_registers_ssid_into_the_secret_registry_when_given_one() -> None:
    registry = SecretRegistry()

    def fake_http_post(url: str, *, json: Mapping[str, Any]) -> _FakeResponse:
        return _FakeResponse(status_code=200, _body=_success_body())

    login(_EMAIL, _PASSWORD, http_post=fake_http_post, registry=registry)

    assert _SSID in registry.values


def test_login_raises_login_error_on_non_success_code() -> None:
    def fake_http_post(url: str, *, json: Mapping[str, Any]) -> _FakeResponse:
        return _FakeResponse(status_code=200, _body={"code": "error", "message": "bad credentials"})

    with pytest.raises(LoginError):
        login(_EMAIL, _PASSWORD, http_post=fake_http_post)


def test_login_raises_login_error_on_http_error_status() -> None:
    def fake_http_post(url: str, *, json: Mapping[str, Any]) -> _FakeResponse:
        return _FakeResponse(status_code=500, _body={"code": "success", "ssid": _SSID})

    with pytest.raises(LoginError):
        login(_EMAIL, _PASSWORD, http_post=fake_http_post)


def test_login_raises_login_error_when_transport_raises() -> None:
    def fake_http_post(url: str, *, json: Mapping[str, Any]) -> _FakeResponse:
        raise ConnectionError("network unreachable")

    with pytest.raises(LoginError):
        login(_EMAIL, _PASSWORD, http_post=fake_http_post)


def test_login_raises_login_error_when_ssid_missing_from_success_response() -> None:
    def fake_http_post(url: str, *, json: Mapping[str, Any]) -> _FakeResponse:
        return _FakeResponse(status_code=200, _body={"code": "success"})

    with pytest.raises(LoginError):
        login(_EMAIL, _PASSWORD, http_post=fake_http_post)
