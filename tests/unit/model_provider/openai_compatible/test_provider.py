from typing import Any

import httpx2
import pytest
from pydantic import ValidationError

from app.config.schema import OpenAICompatibleProviderConfig, ProxyConfig
from app.model_provider import (
    CatalogProvider,
    ModelEndpoint,
    OpenAICompatibleProvider,
    ProviderRegistry,
)
from app.model_provider.openai_compatible import OpenAICompatibleClient
from app.model_provider.types import CapabilityMissing
from app.pipeline.exceptions import UpstreamRejected
from app.pipeline.request import WireFormat
from app.pipeline.routing import decide_route
from app.wire_json import loads


def config(**overrides: Any) -> OpenAICompatibleProviderConfig:
    values: dict[str, Any] = {
        "type": "sub2api",
        "api_base_url": "https://ttthree.example/v1",
        "api_key": "test-key",
        "models": ["configured-model"],
    }
    values.update(overrides)
    return OpenAICompatibleProviderConfig.model_validate(values)


def test_ttthree_name_can_use_the_sub2api_provider_type() -> None:
    proxy = ProxyConfig.model_validate(
        {
            "model_providers": {
                "ttthree": {
                    "type": "sub2api",
                    "api_base_url": "https://ttthree.example/v1",
                    "api_key": "test-key",
                }
            },
            "default_model_provider": "ttthree",
        }
    )

    provider = proxy.model_providers["ttthree"]
    assert isinstance(provider, OpenAICompatibleProviderConfig)
    assert "test-key" not in repr(provider)


def test_sub2api_provider_requires_an_api_base_url() -> None:
    with pytest.raises(ValidationError):
        OpenAICompatibleProviderConfig.model_validate({"type": "sub2api"})


@pytest.mark.parametrize("provider_type", ["openai_compatible", "openai"])
def test_legacy_provider_types_are_rejected(provider_type: str) -> None:
    with pytest.raises(ValidationError):
        ProxyConfig.model_validate(
            {
                "model_providers": {
                    "ttthree": {
                        "type": provider_type,
                        "api_base_url": "https://ttthree.example/v1",
                    }
                }
            }
        )


@pytest.mark.parametrize(
    "api_base_url",
    [
        "127.0.0.1:9000/v1",
        "https://example.com:0/v1",
        "https://example.com:bad/v1",
        " https://example.com/v1",
    ],
)
def test_sub2api_provider_rejects_an_invalid_api_base_url(
    api_base_url: str,
) -> None:
    with pytest.raises(ValidationError):
        OpenAICompatibleProviderConfig.model_validate(
            {"type": "sub2api", "api_base_url": api_base_url}
        )


def test_endpoint_settings_accept_enabled_bool_url_and_empty() -> None:
    provider = OpenAICompatibleProviderConfig.model_validate(
        {
            "type": "sub2api",
            "api_base_url": "https://ttthree.example/v1",
            "openai_chat_completions_endpoint": True,
            "openai_responses_endpoint": "https://proxy.example/alt/responses",
            "anthropic_messages_endpoint": "",
        }
    )
    assert provider.openai_chat_completions_endpoint is True
    assert provider.openai_responses_endpoint == "https://proxy.example/alt/responses"
    assert provider.anthropic_messages_endpoint == ""


@pytest.mark.parametrize(
    "value",
    [
        False,  # collapses to disabled
        "https://proxy.example/responses",
    ],
)
def test_endpoint_setting_false_and_url_keep_their_state(value: object) -> None:
    provider = OpenAICompatibleProviderConfig.model_validate(
        {
            "type": "sub2api",
            "api_base_url": "https://ttthree.example/v1",
            "openai_responses_endpoint": value,
        }
    )
    if value is False:
        assert provider.openai_responses_endpoint == ""
    else:
        assert provider.openai_responses_endpoint == "https://proxy.example/responses"


@pytest.mark.parametrize(
    "value",
    [
        "not-a-url",
        "  https://proxy.example/responses",
        "ftp://proxy.example/responses",
    ],
)
def test_endpoint_setting_rejects_a_non_absolute_http_url(value: str) -> None:
    with pytest.raises(ValidationError):
        OpenAICompatibleProviderConfig.model_validate(
            {
                "type": "sub2api",
                "api_base_url": "https://ttthree.example/v1",
                "openai_responses_endpoint": value,
            }
        )


@pytest.mark.asyncio
async def test_configured_models_are_filtered_from_upstream_catalog_and_keep_metadata() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {
                        "id": "configured-model",
                        "supported_endpoints": ["/responses"],
                        "capabilities": {
                            "tokenizer": "o200k_base",
                            "limits": {
                                "max_prompt_tokens": 100,
                                "max_context_window_tokens": 200,
                            },
                        },
                    },
                    {
                        "id": "not-allowed",
                        "supported_endpoints": ["/chat/completions"],
                    },
                ],
            },
        )

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    provider_config = config(openai_responses_endpoint=True)
    provider = OpenAICompatibleProvider(
        "ttthree",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )
    typed_catalog: CatalogProvider = provider

    try:
        assert await provider.refresh_catalog() is True
        descriptor = provider.describe("configured-model")
        assert descriptor is not None
        assert descriptor.endpoints == {ModelEndpoint.OPENAI_RESPONSES}
        assert descriptor.prompt_token_limits is not None
        assert descriptor.prompt_token_limits.max_prompt_tokens == 100
        assert provider.describe("not-allowed") is None
        route = decide_route(
            requested_model="configured-model",
            inbound_format=WireFormat.ANTHROPIC_MESSAGES,
            providers=ProviderRegistry({"ttthree": provider}, default="ttthree"),
            mappings={},
        )
    finally:
        await http_client.aclose()

    assert route.endpoint is ModelEndpoint.OPENAI_RESPONSES
    assert route.translation_required is True
    assert [request.url.path for request in seen] == ["/v1/models"]
    assert typed_catalog.catalog_snapshot.source == "upstream"


@pytest.mark.asyncio
async def test_models_refresh_is_not_static_even_when_an_allowlist_is_configured() -> None:
    http_client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda request: httpx2.Response(
                200,
                json={"object": "list", "data": [{"id": "configured-model"}]},
            )
        )
    )
    provider_config = config()
    provider = OpenAICompatibleProvider(
        "ttthree",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )

    try:
        assert provider.describe("configured-model") is None
        assert await provider.refresh_catalog() is True
        assert provider.describe("configured-model") is not None
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_sub2api_catalog_uses_configured_native_endpoints() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if request.url.path == "/v1/models":
            return httpx2.Response(
                200,
                json={"object": "list", "data": [{"id": "native-model"}]},
            )
        return httpx2.Response(200, json={"type": "message", "content": []})

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    provider_config = config(
        models=["native-model"],
        openai_chat_completions_endpoint=True,
        openai_responses_endpoint=True,
        anthropic_messages_endpoint=True,
    )
    provider = OpenAICompatibleProvider(
        "ttthree",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )

    try:
        await provider.refresh_catalog()
        descriptor = provider.describe("native-model")
        assert descriptor is not None
        assert descriptor.endpoints == {
            ModelEndpoint.ANTHROPIC_MESSAGES,
            ModelEndpoint.OPENAI_RESPONSES,
            ModelEndpoint.OPENAI_CHAT_COMPLETIONS,
        }
        await provider.send(
            ModelEndpoint.ANTHROPIC_MESSAGES,
            {"model": "native-model", "messages": [], "max_tokens": 16},
            descriptor=descriptor,
        )
    finally:
        await http_client.aclose()

    assert [request.url.path for request in seen] == ["/v1/models", "/v1/messages"]


@pytest.mark.asyncio
async def test_sub2api_without_configured_endpoints_has_no_direct_capability() -> None:
    http_client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda request: httpx2.Response(
                200,
                json={"object": "list", "data": [{"id": "native-model"}]},
            )
        )
    )
    provider_config = config(models=["native-model"])
    provider = OpenAICompatibleProvider(
        "ttthree",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )

    try:
        await provider.refresh_catalog()
        descriptor = provider.describe("native-model")
        assert descriptor is not None
        # Nothing declared: the broken-out default removes the old default-all-on,
        # so the model advertises no directly served protocol at all.
        assert descriptor.endpoints == frozenset()
        assert descriptor.unknown_endpoints == ()

        with pytest.raises(CapabilityMissing):
            decide_route(
                requested_model="native-model",
                inbound_format=WireFormat.ANTHROPIC_MESSAGES,
                providers=ProviderRegistry({"ttthree": provider}, default="ttthree"),
                mappings={},
            )
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_sub2api_count_tokens_reaches_the_native_endpoint() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"input_tokens": 5})

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    provider_config = config(models=["native-model"], anthropic_messages_endpoint=True)
    provider = OpenAICompatibleProvider(
        "ttthree",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )
    provider.replace_catalog({"data": [{"id": "native-model"}]})

    try:
        descriptor = provider.describe("native-model")
        assert descriptor is not None
        response = await provider.count_tokens(
            {"model": "native-model", "messages": [{"role": "user", "content": "hello"}]},
            descriptor=descriptor,
        )
    finally:
        await http_client.aclose()

    assert response.json() == {"input_tokens": 5}
    assert [request.url.path for request in seen] == ["/v1/messages/count_tokens"]


@pytest.mark.asyncio
async def test_custom_responses_url_is_used_verbatim() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if request.url.path == "/v1/models":
            return httpx2.Response(
                200,
                json={"object": "list", "data": [{"id": "remote-model"}]},
            )
        return httpx2.Response(200, json={"id": "resp-1", "object": "response"})

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    provider_config = config(
        models=[],
        openai_responses_endpoint="https://alt.example/openai/v1/responses",
    )
    provider = OpenAICompatibleProvider(
        "ttthree",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )

    try:
        await provider.refresh_catalog()
        descriptor = provider.describe("remote-model")
        assert descriptor is not None
        response = await provider.send(
            ModelEndpoint.OPENAI_RESPONSES,
            {"model": "remote-model", "input": "ping"},
            descriptor=descriptor,
        )
    finally:
        await http_client.aclose()

    assert response.status_code == 200
    assert str(seen[1].url) == "https://alt.example/openai/v1/responses"


@pytest.mark.asyncio
async def test_custom_anthropic_url_also_relocates_count_tokens() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"input_tokens": 5})

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    provider_config = config(
        models=["native-model"],
        anthropic_messages_endpoint="https://anthropic-proxy.example/company/messages",
    )
    provider = OpenAICompatibleProvider(
        "ttthree",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )
    provider.replace_catalog({"data": [{"id": "native-model"}]})

    try:
        descriptor = provider.describe("native-model")
        assert descriptor is not None
        await provider.count_tokens(
            {"model": "native-model", "messages": [{"role": "user", "content": "hi"}]},
            descriptor=descriptor,
        )
    finally:
        await http_client.aclose()

    assert str(seen[0].url) == "https://anthropic-proxy.example/company/messages/count_tokens"


@pytest.mark.asyncio
async def test_models_catalog_and_responses_request_use_openai_compatible_wire() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if request.url.path == "/v1/models":
            return httpx2.Response(
                200,
                json={"object": "list", "data": [{"id": "remote-model", "object": "model"}]},
            )
        return httpx2.Response(200, json={"id": "resp-1", "object": "response"})

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    provider_config = config(models=[], openai_responses_endpoint=True)
    provider = OpenAICompatibleProvider(
        "ttthree",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )

    try:
        assert await provider.refresh_catalog() is True
        descriptor = provider.describe("remote-model")
        assert descriptor is not None
        response = await provider.send(
            ModelEndpoint.OPENAI_RESPONSES,
            {"model": "remote-model", "input": "ping"},
            descriptor=descriptor,
        )
    finally:
        await http_client.aclose()

    assert response.status_code == 200
    assert [request.url.path for request in seen] == ["/v1/models", "/v1/responses"]
    assert seen[1].headers["authorization"] == "Bearer test-key"
    assert loads(seen[1].content) == {"model": "remote-model", "input": "ping"}


@pytest.mark.asyncio
async def test_explicit_catalog_chat_endpoint_is_supported() -> None:
    seen: list[httpx2.Request] = []
    http_client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda request: seen.append(request) or httpx2.Response(200, json={"choices": []})
        )
    )
    provider_config = config(models=[], openai_chat_completions_endpoint=True)
    provider = OpenAICompatibleProvider(
        "ttthree",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )

    try:
        provider.replace_catalog(
            {
                "object": "list",
                "data": [
                    {
                        "id": "chat-model",
                        "supported_endpoints": ["/v1/chat/completions"],
                    }
                ],
            }
        )
        descriptor = provider.describe("chat-model")
        assert descriptor is not None
        await provider.send(
            ModelEndpoint.OPENAI_CHAT_COMPLETIONS,
            {"model": "chat-model", "messages": []},
            descriptor=descriptor,
        )
    finally:
        await http_client.aclose()

    assert [request.url.path for request in seen] == ["/v1/chat/completions"]


@pytest.mark.asyncio
async def test_client_preserves_upstream_rejection_and_sent_body() -> None:
    http_client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(400, content=b'{"error":"bad request"}')
        )
    )
    client = OpenAICompatibleClient(http_client, config(openai_responses_endpoint=True))

    try:
        with pytest.raises(UpstreamRejected) as raised:
            await client.send(
                ModelEndpoint.OPENAI_RESPONSES,
                {"model": "configured-model", "input": "bad"},
            )
    finally:
        await http_client.aclose()

    assert raised.value.status_code == 400
    assert raised.value.body_bytes == b'{"error":"bad request"}'
    assert loads(raised.value.sent) == {
        "model": "configured-model",
        "input": "bad",
    }


@pytest.mark.asyncio
async def test_catalog_request_sends_the_configured_api_key() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(
            200,
            json={"object": "list", "data": [{"id": "remote-model"}]},
        )

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    provider_config = config(models=[])
    provider = OpenAICompatibleProvider(
        "ttthree",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )

    try:
        assert await provider.refresh_catalog() is True
    finally:
        await http_client.aclose()

    assert seen[0].headers["authorization"] == "Bearer test-key"
