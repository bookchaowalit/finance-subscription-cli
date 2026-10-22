"""HTTP retry and Google OAuth error handling with urlopen mocked (no network)."""

from __future__ import annotations

import io
import json
import urllib.error
from email.message import Message
from typing import Any

import pytest

from subscription_intelligence import http_util


class _Resp:
    def __init__(self, payload: Any) -> None:
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body


def _http_error(code: int, body: dict[str, Any]) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://example.invalid",
        code,
        "err",
        Message(),
        io.BytesIO(json.dumps(body).encode()),
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_util.time, "sleep", lambda _s: None)


def test_retries_transient_status_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_urlopen(req: Any, timeout: int) -> _Resp:
        calls.append(1)
        if len(calls) == 1:
            raise _http_error(503, {})
        return _Resp({"ok": True})

    monkeypatch.setattr(http_util.urllib.request, "urlopen", fake_urlopen)
    assert http_util.api_request("https://example.invalid") == {"ok": True}
    assert len(calls) == 2


def test_non_retryable_status_raises_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_urlopen(req: Any, timeout: int) -> _Resp:
        calls.append(1)
        raise _http_error(404, {})

    monkeypatch.setattr(http_util.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(urllib.error.HTTPError):
        http_util.api_request("https://example.invalid")
    assert len(calls) == 1


def test_oauth_failure_exposes_only_a_safe_code(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_detail = "refresh token 1//leaky-value revoked"

    def fake_urlopen(req: Any, timeout: int) -> _Resp:
        raise _http_error(400, {"error": "invalid_grant", "error_description": secret_detail})

    monkeypatch.setattr(http_util.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(http_util.GoogleOAuthError) as exc:
        http_util.get_access_token("cid", "csecret", "rtoken")
    assert exc.value.code == "invalid_grant"
    assert secret_detail not in str(exc.value)
    assert exc.value.__cause__ is None


def test_unknown_provider_codes_are_bucketed() -> None:
    assert http_util.GoogleOAuthError("something_new").code == "unknown"


def test_missing_access_token_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        http_util.urllib.request, "urlopen", lambda req, timeout: _Resp({"token_type": "Bearer"})
    )
    with pytest.raises(http_util.GoogleOAuthError):
        http_util.get_access_token("cid", "csecret", "rtoken")


def test_returns_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        http_util.urllib.request, "urlopen", lambda req, timeout: _Resp({"access_token": "at"})
    )
    assert http_util.get_access_token("cid", "csecret", "rtoken") == "at"
