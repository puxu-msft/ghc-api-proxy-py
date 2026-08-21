from pathlib import Path

import pytest

from app.ghc_client.auth.providers import (
    CLITokenProvider,
    DeviceAuthProvider,
    EnvTokenProvider,
    FileTokenProvider,
    GitHubTokenManager,
    GitHubTokenProvider,
    TokenInfo,
    noninteractive_token_available,
)
from app.ghc_client.device_flow import DeviceCode


class StubDeviceFlow:
    def __init__(self) -> None:
        self.device = DeviceCode(
            device_code="device",
            user_code="CODE",
            verification_uri="https://github.com/login/device",
            expires_in=900,
            interval=5,
        )

    async def request_device_code(self) -> DeviceCode:
        return self.device

    async def poll_access_token(self, device: DeviceCode) -> str:
        assert device is self.device
        return "ghu_device"


class StubProvider(GitHubTokenProvider):
    def __init__(
        self,
        *,
        priority: int,
        token: str | None,
        refreshable: bool = False,
    ) -> None:
        self.priority = priority
        self.name = f"stub-{priority}"
        self.refreshable = refreshable
        self.token = token
        self.get_calls = 0
        self.refresh_calls = 0

    async def is_available(self) -> bool:
        return self.token is not None

    async def get_token(self) -> TokenInfo | None:
        self.get_calls += 1
        if self.token is None:
            return None
        return TokenInfo(token=self.token, source="device-auth", refreshable=self.refreshable)

    async def refresh(self) -> TokenInfo | None:
        self.refresh_calls += 1
        return await self.get_token()


@pytest.mark.asyncio
async def test_provider_chain_uses_priority_and_caches_winner() -> None:
    low = StubProvider(priority=4, token="low")
    high = StubProvider(priority=1, token="high")
    manager = GitHubTokenManager([low, high])

    first = await manager.get_token()
    second = await manager.get_token()

    assert first.token == "high"
    assert second is first
    assert high.get_calls == 1
    assert low.get_calls == 0


@pytest.mark.asyncio
async def test_cli_provider_strips_and_returns_explicit_token() -> None:
    provider = CLITokenProvider("  ghp_cli  ")

    assert await provider.is_available() is True
    assert await provider.get_token() == TokenInfo(
        token="ghp_cli",
        source="cli",
        refreshable=False,
    )


@pytest.mark.asyncio
async def test_env_provider_reads_only_this_projects_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ambient `GH_TOKEN` or `GITHUB_TOKEN` must not become the proxy's identity.

    Both are set by `gh auth login` and by most CI runners for whatever runs next, so honouring them made the proxy authenticate as whoever the surrounding shell happened to be. Asserting they are ignored *while set* is the point: asserting only that the new name works would still pass if the old ones were also being read.
    """
    monkeypatch.setenv("GITHUB_TOKEN", "github")
    monkeypatch.setenv("GH_TOKEN", "gh")
    monkeypatch.setenv("COPILOT_API_GITHUB_TOKEN", "copilot")
    monkeypatch.delenv("GHC_API_PROXY_GITHUB_TOKEN", raising=False)

    assert await EnvTokenProvider().get_token() is None

    monkeypatch.setenv("GHC_API_PROXY_GITHUB_TOKEN", "ours")
    token = await EnvTokenProvider().get_token()

    assert token is not None
    assert token.token == "ours"
    assert token.source == "env"


@pytest.mark.asyncio
async def test_file_provider_reads_writes_and_clears_token(tmp_path: Path) -> None:
    token_path = tmp_path / "auth" / "github_token"
    provider = FileTokenProvider(token_path)

    assert await provider.get_token() is None
    await provider.save_token("  file-token  ")
    assert token_path.read_text(encoding="utf-8") == "file-token"
    assert await provider.get_token() == TokenInfo(
        token="file-token",
        source="file",
        refreshable=False,
    )
    await provider.clear_token()
    assert token_path.exists() is False


@pytest.mark.asyncio
async def test_file_provider_treats_unreadable_path_as_unavailable(tmp_path: Path) -> None:
    provider = FileTokenProvider(tmp_path)

    assert await provider.is_available() is False
    assert await provider.get_token() is None


@pytest.mark.asyncio
async def test_manager_refreshes_only_refreshable_winner() -> None:
    provider = StubProvider(priority=1, token="refreshable", refreshable=True)
    manager = GitHubTokenManager([provider])
    await manager.get_token()

    refreshed = await manager.refresh()

    assert refreshed is not None
    assert provider.refresh_calls == 1


@pytest.mark.asyncio
async def test_manager_raises_when_no_provider_succeeds() -> None:
    manager = GitHubTokenManager([StubProvider(priority=1, token=None)])

    with pytest.raises(RuntimeError, match="GitHub token"):
        await manager.get_token()


@pytest.mark.asyncio
async def test_device_provider_persists_interactive_token(tmp_path: Path) -> None:
    file_provider = FileTokenProvider(tmp_path / "github_token")
    provider = DeviceAuthProvider(StubDeviceFlow(), file_provider)

    token = await provider.get_token()

    assert token == TokenInfo(
        token="ghu_device",
        source="device-auth",
        refreshable=True,
    )
    assert await file_provider.get_token() == TokenInfo(
        token="ghu_device",
        source="file",
        refreshable=False,
    )


@pytest.mark.asyncio
async def test_noninteractive_token_probe_checks_env_and_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_path = tmp_path / "github_token"
    # The "nothing available" rung only reads as absence if the developer's own shell is not exporting one.
    monkeypatch.delenv("GHC_API_PROXY_GITHUB_TOKEN", raising=False)

    assert await noninteractive_token_available(None, token_path) is False
    monkeypatch.setenv("GHC_API_PROXY_GITHUB_TOKEN", "from-env")
    assert await noninteractive_token_available(None, token_path) is True
    monkeypatch.delenv("GHC_API_PROXY_GITHUB_TOKEN")
    token_path.write_text("from-file", encoding="utf-8")
    assert await noninteractive_token_available(None, token_path) is True
