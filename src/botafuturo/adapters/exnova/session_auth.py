"""HTTP login against Exnova's REST API (`POST /v2/login`).

Captured protocol (see `docs/spike-report.md`):

    POST https://api.trade.exnova.com/v2/login
    body:    {"identifier": "<email>", "password": "<password>"}
    success: {"code":"success","company_id":15,"created_at":<ts>,
              "ssid":"<ssid>","token":"<token>","user_id":<id>}

`login()` is the ONE call site in this adapter allowed to unwrap the
`SecretStr` email/password values (`.get_secret_value()`), at the exact
point of use in the HTTP request body -- the same "unwrap only at the
point of actual use" discipline `cli/wire.py` already follows for
`Settings.exnova_email`/`exnova_password`. Unlike `os.environ`/
`keyring.get_password` reads (governed by `config/secrets.py`'s
`SecretProvider` chokepoint and enforced by
`tests/architecture/test_single_secret_unwrap.py`), unwrapping an
in-memory `SecretStr` that was already resolved elsewhere is not covered
by that AST-scan (it only forbids raw environment/keyring reads), so no
change to that architecture test is required for this adapter.

`http_post` is injectable so callers/tests never need a real network
connection -- the default implementation lazily imports `httpx` so this
module can still be imported (e.g. by architecture tests that import every
module under `src/botafuturo`) without `httpx` necessarily being on the
import path at collection time for unrelated tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Protocol

from pydantic import SecretStr

from botafuturo.adapters.logging.redaction import SecretRegistry

DEFAULT_LOGIN_URL = "https://api.trade.exnova.com/v2/login"
_LOGIN_ORIGIN_HEADER = "https://trade.exnova.com"
_SUCCESS_CODE = "success"


class LoginError(Exception):
    """Raised when the Exnova login call fails: a transport-level error, an
    HTTP error status, a non-'success' `code` in the response body, or a
    'success' response missing the `ssid` field this adapter needs."""


@dataclass(frozen=True)
class LoginResult:
    """The outcome of a successful login call."""

    ssid: SecretStr
    user_id: Optional[int]
    company_id: Optional[int]


class HttpResponse(Protocol):
    """Minimal duck-typed shape `login()` needs from an HTTP response --
    matches both `httpx.Response` and any fake used in tests."""

    status_code: int

    def json(self) -> Mapping[str, Any]: ...


class HttpPost(Protocol):
    def __call__(self, url: str, *, json: Mapping[str, Any]) -> HttpResponse: ...


def _default_http_post(url: str, *, json: Mapping[str, Any]) -> HttpResponse:
    import httpx

    return httpx.post(
        url,
        json=json,
        headers={"Origin": _LOGIN_ORIGIN_HEADER},
        timeout=10.0,
    )


def login(
    email: SecretStr,
    password: SecretStr,
    *,
    url: str = DEFAULT_LOGIN_URL,
    http_post: HttpPost = _default_http_post,
    registry: Optional[SecretRegistry] = None,
) -> LoginResult:
    """Log in against Exnova's REST API and return the session `ssid`.

    `registry`, when given, has the resolved `ssid` registered into it
    immediately (the same redaction chokepoint `cli/wire.py` registers
    `exnova_email`/`exnova_password` into) since a live `ssid` is itself a
    credential that must never leak into logs/journals.

    Raises:
        LoginError: on any failure to obtain a usable `ssid` (transport
            error, HTTP error status, non-'success' response code, or a
            'success' response missing `ssid`).
    """
    body = {
        "identifier": email.get_secret_value(),
        "password": password.get_secret_value(),
    }

    try:
        response = http_post(url, json=body)
    except Exception as exc:  # noqa: BLE001 - re-raised as a clear domain error
        raise LoginError(f"Exnova login request failed: {exc}") from exc

    status_code = getattr(response, "status_code", None)
    if status_code is not None and status_code >= 400:
        raise LoginError(f"Exnova login failed with HTTP status {status_code}")

    try:
        response_body = response.json()
    except Exception as exc:  # noqa: BLE001
        raise LoginError(f"Exnova login response was not valid JSON: {exc}") from exc

    if response_body.get("code") != _SUCCESS_CODE:
        raise LoginError(f"Exnova login failed: response code={response_body.get('code')!r}")

    ssid = response_body.get("ssid")
    if not ssid:
        raise LoginError("Exnova login response missing required 'ssid' field")

    if registry is not None:
        registry.register(ssid)

    return LoginResult(
        ssid=SecretStr(ssid),
        user_id=response_body.get("user_id"),
        company_id=response_body.get("company_id"),
    )
