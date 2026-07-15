import time
from collections.abc import Callable
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
        validity_margin: float = 60.0,
    ) -> None:
        self._github_tokens = github_tokens
        self._http = http_client
        self._clock = clock
        self._validity_margin = validity_margin
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

    async def refresh(self, *, force: bool = False) -> CopilotTokenInfo:
        async with self._lock:
            if not force and self._is_valid():
                assert self._current is not None
                return self._current
            github = await self._github_tokens.get_token()
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