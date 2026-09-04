from typing import Any
from uuid import UUID

import httpx2
import pytest

from app.config.schema import XingchenProviderConfig
from app.model_provider import (
    CatalogProvider,
    EndpointNotSupported,
    ModelEndpoint,
    ModelProvider,
    UnknownModel,
)
from app.model_provider.xingchen import XingchenClient, XingchenProvider

NONCE = UUID("11111111-2222-4333-8444-555555555555")
REQUEST_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")


def config(**overrides: Any) -> XingchenProviderConfig:
    values: dict[str, Any] = {
        "type": "xingchen",
        "models": ["chat-pro", "chat-lite"],
        "gateway_api_key": "gateway-key",
        "x_token": "first.second.third",
        "device_id": "device",
        "install_id": "install",
        "disabled_models": ["chat-lite", "stale-name"],
    }
    values.update(overrides)
    return XingchenProviderConfig.model_validate(values)


def make_provider(
    handler: httpx2.MockTransport,
    provider_config: XingchenProviderConfig | None = None,
) -> tuple[XingchenProvider, httpx2.AsyncClient]:
    http_client = httpx2.AsyncClient(transport=handler)
    sequence = iter((NONCE, REQUEST_ID))
    configured = provider_config or config()
    client = XingchenClient(http_client, configured, uuid_factory=lambda: next(sequence))
    return XingchenProvider("xingchen", client, configured), http_client


def test_static_catalog_is_chat_only_and_preserves_disabled_arithmetic() -> None:
    provider, _ = make_provider(httpx2.MockTransport(lambda _: httpx2.Response(200)))
    typed_provider: ModelProvider = provider
    typed_catalog: CatalogProvider = provider

    assert typed_provider.name == "xingchen"
    assert typed_provider.available_ids == {"chat-pro"}
    assert typed_provider.disabled_ids == {"chat-lite"}
    assert typed_provider.catalog_refreshed_at
    assert typed_catalog.catalog_snapshot.source == "static"
    assert typed_catalog.catalog_snapshot.driven_endpoints == {
        ModelEndpoint.OPENAI_CHAT_COMPLETIONS
    }
    assert typed_catalog.catalog_snapshot.raw == {
        "object": "list",
        "data": [
            {
                "id": "chat-pro",
                "object": "model",
                "supported_endpoints": ["/chat/completions"],
                "capabilities": {"type": "chat"},
            },
            {
                "id": "chat-lite",
                "object": "model",
                "supported_endpoints": ["/chat/completions"],
                "capabilities": {"type": "chat"},
            },
        ],
    }

    descriptor = provider.describe("chat-pro")
    assert descriptor is not None
    assert descriptor.endpoints == {ModelEndpoint.OPENAI_CHAT_COMPLETIONS}
    assert provider.describe("chat-lite") is None


@pytest.mark.asyncio
async def test_static_catalog_refresh_is_a_network_free_noop() -> None:
    seen: list[httpx2.Request] = []
    provider, http_client = make_provider(
        httpx2.MockTransport(
            lambda request: seen.append(request) or httpx2.Response(200)
        )
    )
    before = provider.catalog_refreshed_at

    try:
        assert await provider.refresh_catalog() is False
    finally:
        await http_client.aclose()

    assert provider.catalog_refreshed_at == before
    assert seen == []


@pytest.mark.asyncio
async def test_chat_endpoint_is_sent() -> None:
    seen: list[httpx2.Request] = []
    provider, http_client = make_provider(
        httpx2.MockTransport(
            lambda request: seen.append(request) or httpx2.Response(200, json={"choices": []})
        )
    )

    try:
        response = await provider.send(
            ModelEndpoint.OPENAI_CHAT_COMPLETIONS,
            {"model": "chat-pro"},
            model_id="chat-pro",
        )
    finally:
        await http_client.aclose()

    assert response.status_code == 200
    assert [request.url.path for request in seen] == [
        "/superCowork/sapi/api/v1/chat/completions"
    ]


@pytest.mark.asyncio
async def test_unknown_disabled_and_unsupported_requests_never_reach_the_network() -> None:
    seen: list[httpx2.Request] = []
    provider, http_client = make_provider(
        httpx2.MockTransport(
            lambda request: seen.append(request) or httpx2.Response(200)
        )
    )

    try:
        with pytest.raises(UnknownModel):
            await provider.send(
                ModelEndpoint.OPENAI_CHAT_COMPLETIONS,
                {"model": "unknown"},
                model_id="unknown",
            )
        with pytest.raises(UnknownModel):
            await provider.send(
                ModelEndpoint.OPENAI_CHAT_COMPLETIONS,
                {"model": "chat-lite"},
                model_id="chat-lite",
            )
        with pytest.raises(EndpointNotSupported):
            await provider.send(
                ModelEndpoint.ANTHROPIC_MESSAGES,
                {"model": "chat-pro"},
                model_id="chat-pro",
            )
        with pytest.raises(EndpointNotSupported):
            await provider.send(
                ModelEndpoint.OPENAI_RESPONSES,
                {"model": "chat-pro"},
                model_id="chat-pro",
            )
        with pytest.raises(EndpointNotSupported):
            await provider.send(
                ModelEndpoint.OPENAI_EMBEDDINGS,
                {"model": "chat-pro"},
                model_id="chat-pro",
            )
    finally:
        await http_client.aclose()

    assert seen == []


@pytest.mark.asyncio
async def test_count_tokens_is_always_refused_before_the_network() -> None:
    seen: list[httpx2.Request] = []
    provider, http_client = make_provider(
        httpx2.MockTransport(
            lambda request: seen.append(request) or httpx2.Response(200)
        )
    )

    try:
        with pytest.raises(EndpointNotSupported):
            await provider.count_tokens({"model": "chat-pro"}, model_id="chat-pro")
        with pytest.raises(UnknownModel):
            await provider.count_tokens({"model": "unknown"}, model_id="unknown")
        with pytest.raises(UnknownModel):
            await provider.count_tokens({"model": "chat-lite"}, model_id="chat-lite")
    finally:
        await http_client.aclose()

    assert seen == []
