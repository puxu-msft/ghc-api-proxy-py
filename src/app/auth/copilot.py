import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import anyio
import httpx

from app.auth.providers import GitHubTokenManager

TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"
COPILOT_INTERNAL_API_VERSION = "2025-04-01"


@dataclass(frozen=True, slots=True)
class CopilotTokenInfo:
    token: str
    expires_at: float
    refresh_in: int
    raw: dict[str, Any]


class CopilotTokenManager:
    def __init__(
        self,
        github_tokens: GitHubTokenManager,
        http_client: httpx.AsyncClient,
        *,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
        validity_margin: float = 60.0,
        minimum_refresh_interval: float = 60.0,
        max_exchange_attempts: int = 3,
    ) -> None:
        self._github_tokens = github_tokens
        self._http = http_client
        self._clock = clock
        self._sleep = sleep
        self._validity_margin = validity_margin
        self._minimum_refresh_interval = minimum_refresh_interval
        self._max_exchange_attempts = max_exchange_attempts
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

    def next_refresh_delay(self, *, refresh_in: int) -> float:
        return max(float(refresh_in) - self._validity_margin, self._minimum_refresh_interval)

    async def run_refresh_loop(self) -> None:
        info: CopilotTokenInfo | None = self._current
        while True:
            delay = (
                self.next_refresh_delay(refresh_in=info.refresh_in)
                if info is not None
                else self._minimum_refresh_interval
            )
            await self._sleep(delay)
            try:
                info = await self.refresh(force=True)
            except Exception:
                await self._sleep(self._minimum_refresh_interval)

    async def refresh(self, *, force: bool = False) -> CopilotTokenInfo:
        async with self._lock:
            if not force and self._is_valid():
                assert self._current is not None
                return self._current
            raw = await self._exchange_with_retry()
            try:
                info = CopilotTokenInfo(
                    token=str(raw["token"]),
                    expires_at=float(raw["expires_at"]),
                    refresh_in=int(raw["refresh_in"]),
                    raw=raw,
                )
            except (KeyError, TypeError, ValueError) as error:
                raise RuntimeError("invalid Copilot token response") from error
            self._current = info
            return info

    async def _exchange_with_retry(self) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self._max_exchange_attempts):
            github = await self._github_tokens.get_token()
            try:
                response = await self._http.get(
                    TOKEN_URL,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"token {github.token}",
                        "X-GitHub-Api-Version": COPILOT_INTERNAL_API_VERSION,
                    },
                )
                response.raise_for_status()
                raw: dict[str, Any] = response.json()
                return raw
            except (httpx.HTTPError, OSError) as error:
                last_error = error
                status = (
                    error.response.status_code
                    if isinstance(error, httpx.HTTPStatusError)
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