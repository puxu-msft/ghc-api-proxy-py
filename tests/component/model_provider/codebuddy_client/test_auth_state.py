"""The desktop login state: discovery, expiry, refresh, and the write-back that keeps
the desktop app's session current.
"""

import json
import time
from typing import Any

import httpx2
import pytest

from app.model_provider.codebuddy_client.auth_state import (
    AuthRefreshFailed,
    AuthStateInvalid,
    AuthStateMissing,
    CodebuddyCredentials,
    DesktopAuthState,
    discover_auth_file,
)
from app.model_provider.codebuddy_client.config import CodebuddyClientConfig

BACKEND = "https://copilot.tencent.com"


def write_state(
    path: Any,
    *,
    access_token: str = "access-old",
    refresh_token: str = "refresh-1",
    expires_at: int | None = None,
) -> None:
    path.write_text(
        json.dumps(
            {
                "auth": {
                    "accessToken": access_token,
                    "refreshToken": refresh_token,
                    "expiresAt": expires_at if expires_at is not None else int(time.time() * 1000) + 3_600_000,
                    "domain": "www.codebuddy.cn",
                },
                "account": {"uid": "u-1", "enterpriseId": "e-9", "nickname": "tester"},
            }
        ),
        encoding="utf-8",
    )


def test_discovery_finds_the_first_info_file(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEBUDDY_AUTH_DIR", str(tmp_path))
    (tmp_path / "b.info").write_text("{}", encoding="utf-8")
    (tmp_path / "a.info").write_text("{}", encoding="utf-8")

    assert discover_auth_file() == str(tmp_path / "a.info")


def test_discovery_is_empty_when_nothing_is_there(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEBUDDY_AUTH_DIR", str(tmp_path / "absent"))

    assert discover_auth_file() == ""


def test_an_unreadable_state_is_reported_not_raised_as_oserror(tmp_path: Any) -> None:
    state = DesktopAuthState(str(tmp_path / "missing.info"))

    with pytest.raises(AuthStateMissing):
        state.summary()


def test_a_state_without_an_auth_object_is_invalid(tmp_path: Any) -> None:
    path = tmp_path / "state.info"
    path.write_text("{}", encoding="utf-8")
    state = DesktopAuthState(str(path))

    with pytest.raises(AuthStateInvalid):
        state.summary()


def test_an_expired_token_is_detected_with_margin(tmp_path: Any) -> None:
    path = tmp_path / "state.info"
    write_state(path, expires_at=int(time.time() * 1000) + 30_000)
    state = DesktopAuthState(str(path))

    # Inside the 60-second validity margin: already worth refreshing.
    assert state.is_expired()


def test_a_fresh_token_is_not_expired(tmp_path: Any) -> None:
    path = tmp_path / "state.info"
    write_state(path, expires_at=int(time.time() * 1000) + 3_600_000)
    state = DesktopAuthState(str(path))

    assert not state.is_expired()


def test_a_state_without_an_expiry_is_treated_as_expired(tmp_path: Any) -> None:
    path = tmp_path / "state.info"
    path.write_text(json.dumps({"auth": {"accessToken": "a"}, "account": {}}), encoding="utf-8")
    state = DesktopAuthState(str(path))

    assert state.is_expired()


def _refresh_transport(observer: dict[str, Any]) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        observer["refresh_headers"] = dict(request.headers)
        observer["refresh_body"] = request.read()
        return httpx2.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "accessToken": "access-new",
                    "refreshToken": "refresh-2",
                    "expiresIn": 3600,
                },
            },
        )

    return httpx2.MockTransport(handler)


async def test_refresh_posts_the_refresh_token_and_writes_back(tmp_path: Any) -> None:
    path = tmp_path / "state.info"
    write_state(path, expires_at=0)  # already expired
    observer: dict[str, Any] = {}
    http_client = httpx2.AsyncClient(transport=_refresh_transport(observer))
    config = CodebuddyClientConfig()
    credentials = CodebuddyCredentials(DesktopAuthState(str(path)), http_client, config)

    headers = await credentials.request_headers()

    await http_client.aclose()
    assert headers["Authorization"] == "Bearer access-new"
    assert observer["refresh_headers"]["x-refresh-token"] == "refresh-1"
    assert observer["refresh_headers"]["x-auth-refresh-source"] == "plugin"
    assert observer["refresh_headers"]["x-user-id"] == "u-1"
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["auth"]["accessToken"] == "access-new"
    # expiresIn was turned into an absolute expiry the next expiry check can read.
    assert written["auth"]["expiresAt"] > int(time.time() * 1000)
    # Fields the refresh response does not carry are inherited.
    assert written["auth"]["domain"] == "www.codebuddy.cn"
    assert written["account"]["uid"] == "u-1"


async def test_a_refused_refresh_raises(tmp_path: Any) -> None:
    path = tmp_path / "state.info"
    write_state(path, expires_at=0)

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"code": 40001, "msg": "bad refresh token"})

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    credentials = CodebuddyCredentials(
        DesktopAuthState(str(path)), http_client, CodebuddyClientConfig()
    )

    with pytest.raises(AuthRefreshFailed):
        await credentials.request_headers()
    await http_client.aclose()


async def test_a_fresh_token_skips_the_refresh_call(tmp_path: Any) -> None:
    path = tmp_path / "state.info"
    write_state(path)
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(200, json={"code": 1, "msg": "must not be reached"})

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    credentials = CodebuddyCredentials(
        DesktopAuthState(str(path)), http_client, CodebuddyClientConfig()
    )

    headers = await credentials.request_headers()

    await http_client.aclose()
    assert calls == []
    assert headers["Authorization"] == "Bearer access-old"
    assert headers["X-User-Id"] == "u-1"
    assert headers["X-Enterprise-Id"] == "e-9"
    assert headers["X-Tenant-Id"] == "e-9"
    assert headers["X-Domain"] == "www.codebuddy.cn"


async def test_caller_extras_do_not_override_owned_headers(tmp_path: Any) -> None:
    path = tmp_path / "state.info"
    write_state(path)
    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(lambda request: httpx2.Response(200)))
    credentials = CodebuddyCredentials(
        DesktopAuthState(str(path)), http_client, CodebuddyClientConfig()
    )

    headers = await credentials.request_headers(
        extra_headers={"Authorization": "Bearer forwarded", "X-Custom": "1"}
    )

    await http_client.aclose()
    assert headers["Authorization"] == "Bearer access-old"
    assert headers["X-Custom"] == "1"
