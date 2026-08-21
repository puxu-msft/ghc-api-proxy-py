import httpx2
import pytest

from app.ghc_client.account import GitHubAccountClient, infer_account_type


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"copilot_plan": "enterprise"}, "enterprise"),
        ({"access_type_sku": "copilot_for_business"}, "business"),
        ({"copilot_plan": "pro_plus"}, "individual"),
        ({"copilot_plan": "free"}, "individual"),
        ({}, None),
        ({"copilot_plan": "future-plan"}, None),
    ],
)
def test_infer_account_type(payload: dict[str, object], expected: str | None) -> None:
    assert infer_account_type(payload) == expected


@pytest.mark.asyncio
async def test_github_client_gets_user_and_usage_with_token_headers() -> None:
    paths: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        paths.append(request.url.path)
        assert request.headers["authorization"] == "token ghu_test"
        if request.url.path == "/user":
            return httpx2.Response(200, json={"login": "octocat", "future": True})
        return httpx2.Response(200, json={"copilot_plan": "business", "future": True})

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    client = GitHubAccountClient(http_client)
    try:
        user = await client.get_user("ghu_test")
        usage = await client.get_copilot_usage("ghu_test")
    finally:
        await http_client.aclose()

    assert paths == ["/user", "/copilot_internal/user"]
    assert user["login"] == "octocat"
    assert usage["future"] is True


@pytest.mark.asyncio
async def test_copilot_usage_uses_internal_api_version() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.headers["x-github-api-version"] == "2025-04-01"
        return httpx2.Response(200, json={"copilot_plan": "individual"})

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http_client:
        await GitHubAccountClient(http_client).get_copilot_usage("ghu")
