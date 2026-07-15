from pathlib import Path

import pytest

from app.auth.providers import (
    CLITokenProvider,
    EnvTokenProvider,
    FileTokenProvider,
    GitHubTokenManager,
    GitHubTokenProvider,
    TokenInfo,
)


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
async def test_env_provider_uses_documented_variable_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "github")
    monkeypatch.setenv("GH_TOKEN", "gh")
    monkeypatch.setenv("COPILOT_API_GITHUB_TOKEN", "copilot")

    token = await EnvTokenProvider().get_token()

    assert token is not None
    assert token.token == "copilot"
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