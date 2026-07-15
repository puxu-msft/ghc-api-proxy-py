import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from anyio.to_thread import run_sync

from app.auth.device_flow import DeviceCode
from app.config.paths import user_data_path

type TokenSource = Literal["cli", "env", "file", "device-auth"]


@dataclass(frozen=True, slots=True)
class TokenInfo:
    token: str
    source: TokenSource
    expires_at: float | None = None
    refreshable: bool = False


class GitHubTokenProvider(ABC):
    name: str
    priority: int
    refreshable: bool

    @abstractmethod
    async def is_available(self) -> bool: ...

    @abstractmethod
    async def get_token(self) -> TokenInfo | None: ...

    async def refresh(self) -> TokenInfo | None:
        return None


class CLITokenProvider(GitHubTokenProvider):
    name = "CLI"
    priority = 1
    refreshable = False

    def __init__(self, token: str | None = None) -> None:
        self._token = token.strip() if token and token.strip() else None

    async def is_available(self) -> bool:
        return self._token is not None

    async def get_token(self) -> TokenInfo | None:
        if self._token is None:
            return None
        return TokenInfo(token=self._token, source="cli")


class EnvTokenProvider(GitHubTokenProvider):
    name = "Environment"
    priority = 2
    refreshable = False
    variable_names = (
        "COPILOT_API_GITHUB_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
    )

    def _find_token(self) -> str | None:
        for name in self.variable_names:
            value = os.environ.get(name, "").strip()
            if value:
                return value
        return None

    async def is_available(self) -> bool:
        return self._find_token() is not None

    async def get_token(self) -> TokenInfo | None:
        token = self._find_token()
        if token is None:
            return None
        return TokenInfo(token=token, source="env")


class FileTokenProvider(GitHubTokenProvider):
    name = "File"
    priority = 3
    refreshable = False

    def __init__(self, token_path: Path | None = None) -> None:
        self.path = token_path or user_data_path() / "github_token"

    async def is_available(self) -> bool:
        return await self.get_token() is not None

    async def get_token(self) -> TokenInfo | None:
        def read() -> str:
            return self.path.read_text(encoding="utf-8")

        try:
            content = await run_sync(read)
        except OSError:
            return None
        token = content.strip()
        if not token:
            return None
        return TokenInfo(token=token, source="file")

    async def save_token(self, token: str) -> None:
        normalized = token.strip()
        if not normalized:
            raise ValueError("GitHub token cannot be empty")

        def write() -> None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(normalized, encoding="utf-8")
            self.path.chmod(0o600)

        await run_sync(write)

    async def clear_token(self) -> None:
        def unlink() -> None:
            self.path.unlink(missing_ok=True)

        await run_sync(unlink)


class DeviceFlow(Protocol):
    async def request_device_code(self) -> DeviceCode: ...

    async def poll_access_token(self, device: DeviceCode) -> str: ...


class DeviceAuthProvider(GitHubTokenProvider):
    name = "DeviceAuth"
    priority = 4
    refreshable = True

    def __init__(self, device_flow: DeviceFlow, file_provider: FileTokenProvider) -> None:
        self._device_flow = device_flow
        self._file_provider = file_provider

    async def is_available(self) -> bool:
        return True

    async def get_token(self) -> TokenInfo | None:
        device = await self._device_flow.request_device_code()
        token = await self._device_flow.poll_access_token(device)
        await self._file_provider.save_token(token)
        return TokenInfo(token=token, source="device-auth", refreshable=True)

    async def refresh(self) -> TokenInfo | None:
        return await self.get_token()


class GitHubTokenManager:
    def __init__(self, providers: list[GitHubTokenProvider]) -> None:
        self._providers = sorted(providers, key=lambda provider: provider.priority)
        self._current: TokenInfo | None = None
        self._current_provider: GitHubTokenProvider | None = None

    async def get_token(self) -> TokenInfo:
        if self._current is not None:
            return self._current
        for provider in self._providers:
            if not await provider.is_available():
                continue
            token = await provider.get_token()
            if token is None:
                continue
            self._current = token
            self._current_provider = provider
            return token
        raise RuntimeError("No GitHub token provider produced a usable token")

    async def refresh(self) -> TokenInfo | None:
        if self._current is None:
            return await self.get_token()
        provider = self._current_provider
        if provider is None or not self._current.refreshable:
            return None
        refreshed = await provider.refresh()
        if refreshed is not None:
            self._current = refreshed
        return refreshed

    def clear_cache(self) -> None:
        self._current = None
        self._current_provider = None