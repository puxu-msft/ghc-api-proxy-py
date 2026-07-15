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


class RefreshableGitHubProvider(GitHubTokenProvider):
    name = "refreshable"
    priority = 1
    refreshable = True

    def __init__(self) -> None:
        self.token = "old"
        self.refresh_calls = 0

    async def is_available(self) -> bool:
        return True

    async def get_token(self) -> TokenInfo:
        return TokenInfo(token=self.token, source="device-auth", refreshable=True)

    async def refresh(self) -> TokenInfo:
        self.refresh_calls += 1
        self.token = "new"
        return TokenInfo(token=self.token, source="device-auth", refreshable=True)


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


@pytest.mark.asyncio
async def test_exchange_retries_transient_server_error() -> None:
    calls = 0
    sleeps: list[float] = []

    async def no_sleep(delay: float) -> None:
        sleeps.append(delay)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(
            200,
            json={"token": "recovered", "expires_at": 5000, "refresh_in": 1500},
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    manager = CopilotTokenManager(
        GitHubTokenManager([StaticGitHubProvider()]),
        http_client,
        clock=lambda: 1000,
        sleep=no_sleep,
    )
    try:
        assert await manager.get_token() == "recovered"
    finally:
        await http_client.aclose()

    assert calls == 2
    assert sleeps == [1.0]


@pytest.mark.asyncio
async def test_401_refreshes_github_token_before_retry() -> None:
    provider = RefreshableGitHubProvider()
    seen_authorization: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_authorization.append(request.headers["authorization"])
        if len(seen_authorization) == 1:
            return httpx.Response(401, json={"error": "expired"})
        return httpx.Response(
            200,
            json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    manager = CopilotTokenManager(
        GitHubTokenManager([provider]),
        http_client,
        clock=lambda: 1000,
    )
    try:
        assert await manager.get_token() == "copilot"
    finally:
        await http_client.aclose()

    assert provider.refresh_calls == 1
    assert seen_authorization == ["token old", "token new"]


def test_next_refresh_delay_uses_server_hint_with_safety_margin() -> None:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500)))
    manager = CopilotTokenManager(
        GitHubTokenManager([StaticGitHubProvider()]),
        http_client,
        clock=lambda: 1000,
        minimum_refresh_interval=60,
    )

    assert manager.next_refresh_delay(refresh_in=1500) == 1440
    assert manager.next_refresh_delay(refresh_in=30) == 60


@pytest.mark.asyncio
async def test_refresh_loop_survives_exhausted_refresh_failure() -> None:
    calls = 0

    async def stop_after_retry(delay: float) -> None:
        nonlocal calls
        del delay
        calls += 1
        if calls >= 3:
            raise RuntimeError("stop")

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503, json={"error": "temporary"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    manager = CopilotTokenManager(
        GitHubTokenManager([StaticGitHubProvider()]),
        http_client,
        sleep=stop_after_retry,
        max_exchange_attempts=1,
    )
    try:
        with pytest.raises(RuntimeError, match="stop"):
            await manager.run_refresh_loop()
    finally:
        await http_client.aclose()

    assert calls == 3


@pytest.mark.asyncio
async def test_refresh_loop_survives_invalid_success_payload() -> None:
    sleeps = 0

    async def stop(delay: float) -> None:
        nonlocal sleeps
        del delay
        sleeps += 1
        if sleeps >= 2:
            raise RuntimeError("stop")

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"unexpected": True}))
    )
    manager = CopilotTokenManager(
        GitHubTokenManager([StaticGitHubProvider()]),
        http_client,
        sleep=stop,
    )
    try:
        with pytest.raises(RuntimeError, match="stop"):
            await manager.run_refresh_loop()
    finally:
        await http_client.aclose()

    assert sleeps == 2