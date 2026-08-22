import anyio
import httpx2
import pytest

from app.model_provider.ghc_client.tokens import CopilotTokenManager


class StaticTokenSource:
    async def get_token(self) -> str:
        return "ghu_github"

    async def refresh(self) -> str | None:
        return None


class RefreshableTokenSource:
    def __init__(self) -> None:
        self.token = "old"
        self.refresh_calls = 0

    async def get_token(self) -> str:
        return self.token

    async def refresh(self) -> str | None:
        self.refresh_calls += 1
        self.token = "new"
        return self.token


@pytest.mark.asyncio
async def test_copilot_token_exchange_preserves_raw_response() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(
            200,
            json={
                "token": "tid=copilot",
                "expires_at": 2000,
                "refresh_in": 1500,
                "endpoints": {"api": "https://example.test"},
            },
        )

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    identity_headers = {
        "editor-version": "vscode/1.2.3",
        "editor-plugin-version": "copilot-chat/4.5.6",
        "user-agent": "GitHubCopilotChat/4.5.6",
        "x-vscode-user-agent-library-version": "electron-fetch",
    }
    manager = CopilotTokenManager(
        StaticTokenSource(),
        http_client,
        clock=lambda: 1000,
        identity_headers=identity_headers,
    )
    identity_headers["editor-version"] = "vscode/changed"
    try:
        info = await manager.refresh()
    finally:
        await http_client.aclose()

    assert requests[0].method == "GET"
    assert requests[0].url == "https://api.github.com/copilot_internal/v2/token"
    assert requests[0].headers["authorization"] == "token ghu_github"
    assert requests[0].headers["editor-version"] == "vscode/1.2.3"
    assert requests[0].headers["editor-plugin-version"] == "copilot-chat/4.5.6"
    assert requests[0].headers["user-agent"] == "GitHubCopilotChat/4.5.6"
    assert requests[0].headers["x-vscode-user-agent-library-version"] == "electron-fetch"
    assert info.token == "tid=copilot"
    assert info.raw["endpoints"] == {"api": "https://example.test"}


@pytest.mark.asyncio
async def test_dynamic_token_headers_override_case_variant_identity_headers() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(
            200,
            json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
        )

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    manager = CopilotTokenManager(
        StaticTokenSource(),
        http_client,
        clock=lambda: 1000,
        identity_headers={
            "authorization": "identity-static",
            "X-GITHUB-API-VERSION": "old",
            "editor-version": "vscode/1.2.3",
        },
    )
    try:
        await manager.refresh()
    finally:
        await http_client.aclose()

    assert requests[0].headers.get_list("authorization") == ["token ghu_github"]
    assert requests[0].headers.get_list("x-github-api-version") == ["2025-04-01"]


@pytest.mark.asyncio
async def test_valid_copilot_token_is_cached() -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        del request
        calls += 1
        return httpx2.Response(200, json={"token": "cached", "expires_at": 5000, "refresh_in": 1500})

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    manager = CopilotTokenManager(
        StaticTokenSource(),
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

    async def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        del request
        calls += 1
        await anyio.sleep(0.01)
        return httpx2.Response(200, json={"token": "shared", "expires_at": 5000, "refresh_in": 1500})

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    manager = CopilotTokenManager(
        StaticTokenSource(),
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

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        del request
        calls += 1
        if calls == 1:
            return httpx2.Response(503, json={"error": "temporary"})
        return httpx2.Response(
            200,
            json={"token": "recovered", "expires_at": 5000, "refresh_in": 1500},
        )

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    manager = CopilotTokenManager(
        StaticTokenSource(),
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
    provider = RefreshableTokenSource()
    seen_headers: list[httpx2.Headers] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen_headers.append(request.headers)
        if len(seen_headers) == 1:
            return httpx2.Response(401, json={"error": "expired"})
        return httpx2.Response(
            200,
            json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
        )

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    manager = CopilotTokenManager(
        provider,
        http_client,
        clock=lambda: 1000,
        identity_headers={
            "editor-version": "vscode/1.2.3",
            "editor-plugin-version": "copilot-chat/4.5.6",
            "user-agent": "GitHubCopilotChat/4.5.6",
            "x-vscode-user-agent-library-version": "electron-fetch",
            "authorization": "stale",
            "accept": "stale",
            "x-github-api-version": "stale",
        },
    )
    try:
        assert await manager.get_token() == "copilot"
    finally:
        await http_client.aclose()

    assert provider.refresh_calls == 1
    assert [headers["authorization"] for headers in seen_headers] == [
        "token old",
        "token new",
    ]
    for headers in seen_headers:
        assert headers.get_list("authorization") == [headers["authorization"]]
        assert headers.get_list("accept") == ["application/json"]
        assert headers.get_list("x-github-api-version") == ["2025-04-01"]
        assert headers["editor-version"] == "vscode/1.2.3"
        assert headers["editor-plugin-version"] == "copilot-chat/4.5.6"
        assert headers["user-agent"] == "GitHubCopilotChat/4.5.6"
        assert headers["x-vscode-user-agent-library-version"] == "electron-fetch"


@pytest.mark.asyncio
async def test_exhausted_exchange_reports_the_failure_to_the_caller() -> None:
    """The lazy path propagates. There is no background loop left to swallow this."""
    attempts = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        del request
        attempts += 1
        return httpx2.Response(503, json={"error": "temporary"})

    async def no_sleep(delay: float) -> None:
        del delay

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    manager = CopilotTokenManager(
        StaticTokenSource(),
        http_client,
        sleep=no_sleep,
        max_exchange_attempts=3,
    )
    try:
        # The transport's own error, not one of ours: the exchange gives up and whatever the last
        # attempt raised is what the caller sees. Named rather than caught as `Exception`, so a
        # failure that started arriving as something else would show up here instead of passing.
        with pytest.raises(httpx2.HTTPStatusError):
            await manager.get_token()
    finally:
        await http_client.aclose()

    assert attempts == 3


@pytest.mark.asyncio
async def test_invalid_success_payload_is_reported_to_the_caller() -> None:
    """A 200 whose body is not a token is still a failed exchange, and the caller is the one who has to hear about it."""
    http_client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(lambda _: httpx2.Response(200, json={"unexpected": True}))
    )
    manager = CopilotTokenManager(StaticTokenSource(), http_client)
    try:
        with pytest.raises(RuntimeError, match="invalid Copilot token response"):
            await manager.get_token()
    finally:
        await http_client.aclose()

