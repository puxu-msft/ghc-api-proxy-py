import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol

import anyio
import httpx2

from app.model_provider.ghc_client.config import GITHUB_AUTH_BASE_URL

TOKEN_PATH = "/copilot_internal/v2/token"
COPILOT_INTERNAL_API_VERSION = "2025-04-01"


class GitHubTokenSource(Protocol):
    """Where GitHub tokens come from.

    The library does not care whether the token comes from a flag, an env var, a file or a flow.
    `refresh()` returns `None` when this source cannot produce a new token.
    """

    async def get_token(self) -> str: ...

    async def refresh(self) -> str | None: ...


@dataclass(frozen=True, slots=True)
class CopilotTokenInfo:
    """A Copilot token and when it stops being usable.

    Two fields, because two are read. Upstream also sends `refresh_in`, which this used to parse and require; it was the background loop's schedule, and when that loop went nothing read it any more. Requiring it after that meant an upstream that stopped sending a field we do not use would have failed every exchange — and `raw` keeps the whole response anyway, so nothing is lost by not naming it here.
    """

    token: str
    expires_at: float
    raw: dict[str, Any]


class CopilotTokenManager:
    """Exchanges a GitHub token for a Copilot token and keeps it valid.

    Refreshing is lazy: `get_token()` exchanges when the token it holds is within `validity_margin` of expiring, and not before.
    There is no background loop, ruled 2026-08-22 — one existed and was started from the legacy app factory only, so on the chain actually served it had never run and the lazy path was already carrying the whole job.
    The cost of the choice is that the exchange round-trip lands on whichever request first finds the token stale, rather than on a timer.

    Concurrent `get_token()` callers share a single exchange request via the internal lock.
    """

    def __init__(
        self,
        github_tokens: GitHubTokenSource,
        http_client: httpx2.AsyncClient,
        *,
        auth_base_url: str = GITHUB_AUTH_BASE_URL,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
        validity_margin: float = 60.0,
        max_exchange_attempts: int = 3,
        identity_headers: Mapping[str, str] | None = None,
    ) -> None:
        self._github_tokens = github_tokens
        self._http = http_client
        # Where the GitHub token is exchanged for a Copilot one. Configurable because an
        # enterprise install moves it, and because a hardcoded host made this library impossible
        # to stand up against a local server for testing.
        self._auth_base_url = auth_base_url.rstrip("/")
        self._clock = clock
        self._sleep = sleep
        self._validity_margin = validity_margin
        self._max_exchange_attempts = max_exchange_attempts
        self._identity_headers = MappingProxyType(dict(identity_headers or {}))
        self._current: CopilotTokenInfo | None = None
        self._lock = anyio.Lock()

    def _is_valid(self) -> bool:
        return (
            self._current is not None
            and self._clock() < self._current.expires_at - self._validity_margin
        )

    async def get_token(self) -> str:
        if self._is_valid():
            assert self._current is not None
            return self._current.token
        return (await self.refresh()).token

    async def ensure_valid_token(self) -> None:
        if not self._is_valid():
            await self.refresh()

    async def refresh(self) -> CopilotTokenInfo:
        async with self._lock:
            if self._is_valid():
                assert self._current is not None
                return self._current
            raw = await self._exchange_with_retry()
            try:
                info = CopilotTokenInfo(
                    token=str(raw["token"]),
                    expires_at=float(raw["expires_at"]),
                    raw=raw,
                )
            except (KeyError, TypeError, ValueError) as error:
                raise RuntimeError("invalid Copilot token response") from error
            self._current = info
            return info

    async def _exchange_with_retry(self) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self._max_exchange_attempts):
            github_token = await self._github_tokens.get_token()
            try:
                headers = httpx2.Headers(self._identity_headers)
                headers.update(
                    {
                        "Accept": "application/json",
                        "Authorization": f"token {github_token}",
                        "X-GitHub-Api-Version": COPILOT_INTERNAL_API_VERSION,
                    }
                )
                response = await self._http.get(
                    f"{self._auth_base_url}{TOKEN_PATH}", headers=headers
                )
                response.raise_for_status()
                raw: dict[str, Any] = response.json()
                return raw
            except (httpx2.HTTPError, OSError) as error:
                last_error = error
                status = (
                    error.response.status_code
                    if isinstance(error, httpx2.HTTPStatusError)
                    else None
                )
                if status == 401:
                    refreshed = await self._github_tokens.refresh()
                    if refreshed is not None:
                        continue
                retryable = status in (408, 429) or (status is not None and status >= 500)
                if status is None:
                    retryable = True
                if not retryable or attempt + 1 >= self._max_exchange_attempts:
                    raise
                await self._sleep(float(2**attempt))
        assert last_error is not None
        raise last_error
