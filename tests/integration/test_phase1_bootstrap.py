from collections.abc import Mapping

import httpx
import pytest

from app.config.settings import AppSettings
from app.runtime import RuntimeState
from app.upstream.bootstrap import close_upstream_services, initialize_upstream_services


@pytest.mark.asyncio
async def test_copilot_bootstrap_initializes_typed_runtime_services() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if (
            request.url.host == "api.github.com"
            and request.url.path == "/copilot_internal/v2/token"
        ):
            return httpx.Response(
                200,
                json={
                    "token": "copilot-token",
                    "expires_at": 4_000_000_000,
                    "refresh_in": 1500,
                },
            )
        if request.url.host == "api.github.com" and request.url.path == "/copilot_internal/user":
            return httpx.Response(200, json={"copilot_plan": "business"})
        if request.url.host == "api.business.githubcopilot.com" and request.url.path == "/models":
            return httpx.Response(
                200,
                json={"object": "list", "data": [{"id": "claude-test", "vendor": "Anthropic"}]},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    settings = AppSettings.model_validate({"auth": {"github_token": "ghu_cli"}})
    runtime = RuntimeState(settings=settings)
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        services = await initialize_upstream_services(runtime, http_client=http_client)

        assert runtime.upstream_services is services
        assert runtime.github_token_ready is True
        assert runtime.copilot_token_ready is True
        assert runtime.models_ready is True
        assert services.resolved_account_type == "business"
        assert services.model_catalog.available_ids == frozenset({"claude-test"})
        assert services.model_resolver.resolve("claude-test") == "claude-test"
        assert runtime.is_ready is True
    finally:
        await close_upstream_services(runtime, close_http_client=False)
        await http_client.aclose()

    assert [request.url.path for request in requests] == [
        "/copilot_internal/v2/token",
        "/copilot_internal/user",
        "/models",
    ]


@pytest.mark.asyncio
async def test_generic_bootstrap_requires_base_url_and_api_key() -> None:
    runtime = RuntimeState(settings=AppSettings.model_validate({"upstream": {"type": "generic"}}))

    with pytest.raises(ValueError, match="openai_base_url"):
        await initialize_upstream_services(runtime)


@pytest.mark.asyncio
async def test_model_refresh_loop_survives_catalog_failure() -> None:
    class FailingCatalog:
        async def refresh(self, headers: Mapping[str, str]) -> bool:
            del headers
            raise httpx.ConnectError("temporary")

    sleeps = 0

    async def sleep(delay: float) -> None:
        nonlocal sleeps
        del delay
        sleeps += 1
        if sleeps >= 2:
            raise RuntimeError("stop")

    from app.upstream.bootstrap import run_model_refresh_loop

    with pytest.raises(RuntimeError, match="stop"):
        await run_model_refresh_loop(
            FailingCatalog(),
            lambda: _empty_headers(),
            interval_seconds=1,
            sleep=sleep,
        )

    assert sleeps == 2


@pytest.mark.asyncio
async def test_model_refresh_loop_survives_validation_failure() -> None:
    class InvalidCatalog:
        async def refresh(self, headers: Mapping[str, str]) -> bool:
            del headers
            raise ValueError("invalid model payload")

    sleeps = 0

    async def sleep(delay: float) -> None:
        nonlocal sleeps
        del delay
        sleeps += 1
        if sleeps >= 2:
            raise RuntimeError("stop")

    from app.upstream.bootstrap import run_model_refresh_loop

    with pytest.raises(RuntimeError, match="stop"):
        await run_model_refresh_loop(
            InvalidCatalog(),
            lambda: _empty_headers(),
            interval_seconds=1,
            sleep=sleep,
        )

    assert sleeps == 2


async def _empty_headers() -> dict[str, str]:
    return {}