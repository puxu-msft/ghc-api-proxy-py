import anyio
import httpx
import pytest

from app.auth.copilot import CopilotTokenManager
from app.auth.providers import GitHubTokenManager, GitHubTokenProvider, TokenInfo


class StaticGitHubProvider(GitHubTokenProvider):
    name = "static"
    priority = 1
    refreshable = False

    async def is_available(self) -> bool:
        return True

    async def get_token(self) -> TokenInfo:
        return TokenInfo(token="ghu_github", source="env")


@pytest.mark.asyncio
async def test_copilot_token_exchange_preserves_raw_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "token": "tid=copilot",
                "expires_at": 2000,
                "refresh_in": 1500,
                "endpoints": {"api": "https://example.test"},
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    manager = CopilotTokenManager(
        GitHubTokenManager([StaticGitHubProvider()]),
        http_client,
        clock=lambda: 1000,
    )
    try:
        info = await manager.refresh(force=True)
    finally:
        await http_client.aclose()

    assert requests[0].method == "GET"
    assert requests[0].url == "https://api.github.com/copilot_internal/v2/token"
    assert requests[0].headers["authorization"] == "token ghu_github"
    assert info.token == "tid=copilot"
    assert info.raw["endpoints"] == {"api": "https://example.test"}


@pytest.mark.asyncio
async def test_valid_copilot_token_is_cached() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        return httpx.Response(200, json={"token": "cached", "expires_at": 5000, "refresh_in": 1500})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    manager = CopilotTokenManager(
        GitHubTokenManager([StaticGitHubProvider()]),
        http_client,
        clock=lambda: 1000,
    )
    try:
        assert await manager.get_token() == "cached"
        assert await manager.get_token() == "cached"
    finally:
        await http_client.aclose()

    assert calls == 1


@pytest.mark.asyncio
async def test_concurrent_refresh_is_single_flight() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        await anyio.sleep(0.01)
        return httpx.Response(200, json={"token": "shared", "expires_at": 5000, "refresh_in": 1500})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    manager = CopilotTokenManager(
        GitHubTokenManager([StaticGitHubProvider()]),
        http_client,
        clock=lambda: 1000,
    )
    tokens: list[str] = []

    async def get() -> None:
        tokens.append(await manager.get_token())

    try:
        async with anyio.create_task_group() as task_group:
            for _ in range(10):
                task_group.start_soon(get)
    finally:
        await http_client.aclose()

    assert calls == 1
    assert tokens == ["shared"] * 10