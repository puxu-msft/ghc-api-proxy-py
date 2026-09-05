from typing import Any

import httpx2
import pytest

from app.config.schema import ProxyConfig, XingchenProviderConfig
from app.model_provider import XingchenProvider
from app.model_provider.xingchen import XingchenClient
from app.server.composition import build_chain, resolve_provider_base_urls


def xingchen_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "type": "xingchen",
        "models": ["chat-pro"],
        "gateway_api_key": "gateway-key",
        "x_token": "complete.x.token",
        "device_id": "device-id",
        "install_id": "install-id",
    }
    values.update(overrides)
    return values


def config_with_xingchen(*, mixed: bool = False) -> ProxyConfig:
    providers: dict[str, Any] = {"xingchen": xingchen_values()}
    if mixed:
        providers["ghc"] = {"type": "github_copilot"}
    return ProxyConfig.model_validate(
        {
            "model_providers": providers,
            "default_model_provider": "ghc" if mixed else "xingchen",
        }
    )


def test_build_chain_selects_xingchen_without_constructing_github_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("Xingchen must not construct a GitHub token source")

    monkeypatch.setattr("app.server.composition.build_github_token_source", forbidden)
    bootstrap_client = httpx2.AsyncClient()
    chain = build_chain(config_with_xingchen(), http_client=bootstrap_client)

    try:
        provider = chain.providers.default
        assert isinstance(provider, XingchenProvider)
        assert provider.available_ids == {"chat-pro"}
        assert set(chain.provider_clients) == {"xingchen"}
        assert chain.provider_clients["xingchen"] is not bootstrap_client
    finally:
        import asyncio

        asyncio.run(chain.aclose())
        asyncio.run(bootstrap_client.aclose())

    assert chain.provider_clients["xingchen"].is_closed
    assert bootstrap_client.is_closed


@pytest.mark.asyncio
async def test_mixed_providers_get_distinct_clients_closed_by_the_chain() -> None:
    bootstrap_client = httpx2.AsyncClient()
    chain = build_chain(config_with_xingchen(mixed=True), http_client=bootstrap_client)

    try:
        assert set(chain.providers.names) == {"ghc", "xingchen"}
        assert set(chain.provider_clients) == {"ghc", "xingchen"}
        assert chain.provider_clients["ghc"] is not chain.provider_clients["xingchen"]
    finally:
        await chain.aclose()
        await bootstrap_client.aclose()

    assert all(client.is_closed for client in chain.provider_clients.values())


@pytest.mark.asyncio
async def test_xingchen_is_never_sent_through_the_github_base_url_probe() -> None:
    seen: list[httpx2.Request] = []
    http_client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda request: seen.append(request) or httpx2.Response(500)
        )
    )
    config = config_with_xingchen()

    try:
        resolved = await resolve_provider_base_urls(config, http_client=http_client)
    finally:
        await http_client.aclose()

    assert resolved is config
    assert seen == []


@pytest.mark.asyncio
async def test_injected_provider_instances_do_not_allocate_clients() -> None:
    bootstrap_client = httpx2.AsyncClient()
    provider_client = httpx2.AsyncClient()
    provider_config = config_with_xingchen().model_providers["xingchen"]
    assert isinstance(provider_config, XingchenProviderConfig)
    provider = XingchenProvider(
        "xingchen",
        XingchenClient(provider_client, provider_config),
        provider_config,
    )
    chain = build_chain(
        config_with_xingchen(),
        http_client=bootstrap_client,
        providers={"xingchen": provider},
    )

    try:
        assert chain.provider_clients == {}
    finally:
        await chain.aclose()
        await provider_client.aclose()
        await bootstrap_client.aclose()
