"""The CodeBuddy desktop login state, read from where the desktop app keeps it.

The upstream has no login flow a proxy can drive. The desktop WorkBuddy/CodeBuddy
application holds the session in a `.info` JSON file — `auth` (tokens) and `account`
(who is logged in) — and the backend's refresh endpoint rotates the tokens inside it.
This module reads that file, refreshes the access token when it is near expiry, and
writes the rotated state back to the same file atomically, so the desktop app and this
proxy stay one session rather than racing two refresh tokens.

Reading the file again whenever its mtime moves is what makes sharing with the desktop
app workable: when the app refreshes first, the fresher state is picked up instead of
being overwritten by a stale in-memory copy. The same rule protects our own write-back.
"""

import contextlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, cast

import httpx2
import orjson
from anyio import Lock

from app.model_provider.codebuddy_client.config import DEFAULT_DOMAIN, CodebuddyClientConfig
from app.model_provider.types import ProviderError

# Refresh while the access token is still this far from expiry, so an in-flight
# request never rides a token that dies mid-call. The reference converter uses the
# same margin.
_VALIDITY_MARGIN_SECONDS = 60.0

_logger = logging.getLogger(__name__)


class AuthStateMissing(ProviderError):
    """No desktop login state could be found or read."""


class AuthStateInvalid(ProviderError):
    """The login state exists but does not carry what a request needs."""


class AuthRefreshFailed(ProviderError):
    """The backend refused or failed a token refresh."""


def auth_dirs() -> list[Path]:
    """Where desktop login states live, most-specific first.

    `CODEBUDDY_AUTH_DIR` wins over the platform default so a deployment can point at
    a copy of the state without touching the desktop install.
    """
    env_dir = os.environ.get("CODEBUDDY_AUTH_DIR")
    if env_dir:
        return [Path(env_dir)]
    home = Path.home()
    if sys.platform == "darwin":
        return [
            home / "Library" / "Application Support" / "CodeBuddyExtension" / "Data" / "Public" / "auth"
        ]
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local"))
        return [Path(local) / "CodeBuddyExtension" / "Data" / "Public" / "auth"]
    xdg = os.environ.get("XDG_DATA_HOME", str(home / ".local" / "share"))
    return [Path(xdg) / "CodeBuddyExtension" / "Data" / "Public" / "auth"]


def discover_auth_file() -> str:
    """The first `.info` in the auth dirs, or `""` when there is none.

    Directory order decides, not mtime: the reference takes the first sorted entry and
    has not needed smarter selection, and a tie-break nobody has had a reason to want
    is a rule nobody can check.
    """
    for directory in auth_dirs():
        if directory.is_dir():
            for entry in sorted(directory.glob("*.info")):
                return str(entry)
    return ""


class DesktopAuthState:
    """One `.info` file, re-read whenever it changes on disk."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._cached: dict[str, Any] | None = None
        self._mtime: float = 0.0

    def _load_if_stale(self) -> None:
        if not str(self.path):
            # Built with no path because discovery found nothing and configuration
            # named nothing. The message is the fix: the config key that names one.
            raise AuthStateMissing(
                "no CodeBuddy auth state file; set model_providers.<name>.auth_state_file "
                "to the desktop app's .info login state"
            )
        try:
            mtime = self.path.stat().st_mtime
        except OSError as error:
            raise AuthStateMissing(f"cannot stat auth state file {self.path}: {error}") from error
        if self._cached is not None and mtime == self._mtime:
            return
        try:
            raw = self.path.read_bytes()
        except OSError as error:
            raise AuthStateMissing(f"cannot read auth state file {self.path}: {error}") from error
        try:
            loaded = json.loads(raw)
        except ValueError as error:
            raise AuthStateInvalid(
                f"auth state file {self.path} is not valid JSON: {error}"
            ) from error
        if not isinstance(loaded, dict):
            raise AuthStateInvalid(f"auth state file {self.path} does not hold an object")
        self._cached = loaded
        self._mtime = mtime

    @property
    def state(self) -> dict[str, Any]:
        self._load_if_stale()
        assert self._cached is not None
        return self._cached

    def auth(self) -> dict[str, Any]:
        auth = self.state.get("auth")
        if not isinstance(auth, dict):
            raise AuthStateInvalid(f"auth state file {self.path} has no auth object")
        return cast(dict[str, Any], auth)

    def account(self) -> dict[str, Any]:
        account = self.state.get("account")
        return cast(dict[str, Any], account) if isinstance(account, dict) else {}

    def expires_at(self) -> float:
        """The access token's expiry as seconds since the epoch, or 0 when unstated.

        0 rather than an error: a state without `expiresAt` is treated as already
        expired, which drives a refresh — the only recovery the file offers — instead
        of sending a request whose freshness nobody can vouch for.
        """
        raw = self.auth().get("expiresAt")
        if raw is None:
            return 0.0
        try:
            return float(raw) / 1000.0
        except (TypeError, ValueError):
            return 0.0

    def is_expired(self) -> bool:
        return time.time() >= self.expires_at() - _VALIDITY_MARGIN_SECONDS

    def write_back(self, auth: dict[str, Any]) -> None:
        """Persist rotated tokens into the same file, atomically.

        Written back rather than kept in memory only because the refresh endpoint
        rotates the refresh token: a state that stayed stale on disk would make the
        desktop app's next refresh fail, and the file is the one place both sides read.
        """
        updated = dict(self.state)
        updated["auth"] = auth
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as error:
            # The in-memory copy is still good, so serving continues; the next refresh
            # after a restart will read whatever the desktop app last wrote. Logged so
            # the eventual surprise — a refresh token the backend has since rotated —
            # has a starting point.
            _logger.warning(
                "could not write refreshed auth state back to %s: %s", self.path, error
            )
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
        self._cached = updated
        with contextlib.suppress(OSError):
            self._mtime = self.path.stat().st_mtime

    def summary(self) -> dict[str, Any]:
        """What an operator report wants about the session, and nothing secret."""
        auth = self.auth()
        account = self.account()
        return {
            "uid": account.get("uid", ""),
            "nickname": account.get("nickname", ""),
            "enterprise": account.get("enterpriseName", ""),
            "expires_at": auth.get("expiresAt", 0),
            "expired": self.is_expired(),
        }


class CodebuddyCredentials:
    """Produces authenticated request headers, refreshing the token first when needed.

    The shape mirrors `CopilotTokenManager`: headers are computed per call rather than
    held from construction, because the access token expires and a set captured once
    would authenticate the first request and nothing after it. Concurrent callers share
    one refresh through the lock.
    """

    def __init__(
        self,
        state: DesktopAuthState,
        http_client: httpx2.AsyncClient,
        config: CodebuddyClientConfig,
    ) -> None:
        self._state = state
        self._http = http_client
        self._config = config
        self._lock = Lock()

    async def request_headers(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> dict[str, str]:
        # anyio rather than asyncio: the host process may run either loop, and the
        # sibling token manager already depends on anyio's lock for the same job.
        async with self._lock:
            if self._state.is_expired():
                await self._refresh()
            headers = build_request_headers(self._state, self._config)
        for key, value in (extra_headers or {}).items():
            # Caller extras underneath the owned set, case-insensitively — the same rule
            # `GhcApiClient.request_headers` applies, for the same reason: a forwarded
            # `authorization` must not produce a second header line.
            if not any(existing.lower() == key.lower() for existing in headers):
                headers[key] = value
        return headers

    async def _refresh(self) -> None:
        auth = self._state.auth()
        headers = build_request_headers(self._state, self._config)
        headers["X-Refresh-Token"] = str(auth.get("refreshToken", ""))
        headers["X-Auth-Refresh-Source"] = "plugin"
        url = f"{self._config.api_base_url}/v2/plugin/auth/token/refresh"
        try:
            response = await self._http.post(url, headers=headers, json={})
        except httpx2.HTTPError as error:
            raise AuthRefreshFailed(f"refresh request failed: {error}") from error
        if response.status_code != 200:
            raise AuthRefreshFailed(
                f"refresh answered {response.status_code}: {response.text[:200]}"
            )
        try:
            payload = orjson.loads(response.content)
        except ValueError as error:
            raise AuthRefreshFailed(f"refresh answered unparseable JSON: {error}") from error
        if not isinstance(payload, dict):
            raise AuthRefreshFailed(f"refresh answered an unexpected shape: {payload!r}")
        envelope = cast(dict[str, Any], payload)
        if envelope.get("code") != 0 or not isinstance(envelope.get("data"), dict):
            raise AuthRefreshFailed(f"refresh refused: {envelope.get('msg', envelope)}")
        new_auth = dict[str, Any](cast(dict[str, Any], envelope["data"]))
        # Fields the refresh response does not carry are inherited from the state it
        # replaces — the reference does the same, and `X-Domain` on every later request
        # reads from here.
        new_auth.setdefault("domain", auth.get("domain", ""))
        new_auth["lastRefreshTime"] = int(time.time() * 1000)
        if not new_auth.get("expiresAt") and new_auth.get("expiresIn"):
            new_auth["expiresAt"] = int(time.time() * 1000) + int(new_auth["expiresIn"]) * 1000
        if not new_auth.get("refreshExpiresAt") and new_auth.get("refreshExpiresIn"):
            new_auth["refreshExpiresAt"] = (
                int(time.time() * 1000) + int(new_auth["refreshExpiresIn"]) * 1000
            )
        self._state.write_back(new_auth)

    def summary(self) -> dict[str, Any]:
        return self._state.summary()


def build_request_headers(state: DesktopAuthState, config: CodebuddyClientConfig) -> dict[str, str]:
    """The headers every inference and refresh request carries.

    Measured from the reference converter, which has served this host: the bearer
    token plus the tenant headers the backend reads the account out of. `X-Tenant-Id`
    and `X-Enterprise-Id` carry the same value there, and are sent as two headers
    because the backend reads both names.
    """
    auth = state.auth()
    account = state.account()
    domain = str(auth.get("domain", "")) or DEFAULT_DOMAIN
    enterprise = str(account.get("enterpriseId", ""))
    return {
        "Authorization": f"Bearer {auth.get('accessToken', '')}",
        "X-User-Id": str(account.get("uid", "")),
        "X-Enterprise-Id": enterprise,
        "X-Tenant-Id": enterprise,
        "X-Domain": domain,
        "User-Agent": config.user_agent,
        "Accept": "application/json",
    }
