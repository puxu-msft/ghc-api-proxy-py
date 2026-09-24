import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx2
import pytest
from pydantic import ValidationError

from app.config.schema import (
    NOT_HOT_RELOADABLE,
    PROVIDER_NOT_HOT_RELOADABLE,
    OpenAICompatibleProviderConfig,
    ProxyConfig,
)
from app.model_provider import (
    CatalogProvider,
    ModelEndpoint,
    OpenAICompatibleProvider,
    ProviderRegistry,
)
from app.model_provider.model_info import (
    MODEL_INFO_SCHEMA_VERSION,
    ModelInfoError,
)
from app.model_provider.openai_compatible import OpenAICompatibleClient
from app.model_provider.types import CapabilityMissing
from app.pipeline.exceptions import UpstreamRejected
from app.pipeline.request import WireFormat
from app.pipeline.routing import decide_route
from app.wire_json import loads


def config(**overrides: Any) -> OpenAICompatibleProviderConfig:
    values: dict[str, Any] = {
        "type": "bridge",
        "api_base_url": "https://ttthree.example/v1",
        "api_key": "test-key",
        "models": ["configured-model"],
    }
    values.update(overrides)
    return OpenAICompatibleProviderConfig.model_validate(values)


def test_opencode_zen_uses_the_public_bridge_provider_shape() -> None:
    proxy = ProxyConfig.model_validate(
        {
            "model_providers": {
                "opencode_zen": {
                    "type": "bridge",
                    "api_base_url": "https://opencode.ai/zen/v1",
                    "api_key": "test-key",
                    "openai_chat_completions_endpoint": True,
                    "openai_responses_endpoint": True,
                    "anthropic_messages_endpoint": True,
                }
            },
            "default_model_provider": "opencode_zen",
        }
    )

    provider = proxy.model_providers["opencode_zen"]
    assert isinstance(provider, OpenAICompatibleProviderConfig)
    assert provider.type == "bridge"
    assert provider.api_base_url == "https://opencode.ai/zen/v1"
    assert provider.openai_chat_completions_endpoint is True
    assert provider.openai_responses_endpoint is True
    assert provider.anthropic_messages_endpoint is True
    assert "test-key" not in repr(provider)


def test_bridge_provider_requires_an_api_base_url() -> None:
    with pytest.raises(ValidationError):
        OpenAICompatibleProviderConfig.model_validate({"type": "bridge"})


@pytest.mark.parametrize("provider_type", ["sub2api", "openai_compatible", "openai"])
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
def test_bridge_provider_rejects_an_invalid_api_base_url(
    api_base_url: str,
) -> None:
    with pytest.raises(ValidationError):
        OpenAICompatibleProviderConfig.model_validate(
            {"type": "bridge", "api_base_url": api_base_url}
        )


def test_endpoint_settings_accept_enabled_bool_url_and_empty() -> None:
    provider = OpenAICompatibleProviderConfig.model_validate(
        {
            "type": "bridge",
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
            "type": "bridge",
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
                "type": "bridge",
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
async def test_bridge_catalog_reasoning_efforts_are_projected_to_the_descriptor() -> None:
    http_client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": "configured-model",
                            "supported_endpoints": ["/responses"],
                            "capabilities": {
                                "supports": {
                                    "reasoning_effort": ["low", "medium", "high"]
                                }
                            },
                        }
                    ],
                },
            )
        )
    )
    provider_config = config(openai_responses_endpoint=True)
    provider = OpenAICompatibleProvider(
        "bridge",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )

    try:
        await provider.refresh_catalog()
        descriptor = provider.describe("configured-model")
    finally:
        await http_client.aclose()

    assert descriptor is not None
    assert descriptor.reasoning_efforts == ("low", "medium", "high")


@pytest.mark.asyncio
async def test_bridge_catalog_reasoning_efforts_take_precedence_over_fallback_config() -> None:
    http_client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": "configured-model",
                            "supported_endpoints": ["/responses"],
                            "capabilities": {
                                "supports": {"reasoning_effort": ["high"]}
                            },
                        }
                    ],
                },
            )
        )
    )
    provider_config = config(
        openai_responses_endpoint=True,
        reasoning_efforts={"configured-model": ["xhigh"]},
    )
    provider = OpenAICompatibleProvider(
        "bridge",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )

    try:
        await provider.refresh_catalog()
        descriptor = provider.describe("configured-model")
    finally:
        await http_client.aclose()

    assert descriptor is not None
    assert descriptor.reasoning_efforts == ("high",)


@pytest.mark.asyncio
async def test_configured_reasoning_efforts_fill_a_catalog_gap() -> None:
    http_client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": "configured-model",
                            "supported_endpoints": ["/responses"],
                        }
                    ],
                },
            )
        )
    )
    provider_config = config(
        openai_responses_endpoint=True,
        reasoning_efforts={"configured-model": ["high", "xhigh"]},
    )
    provider = OpenAICompatibleProvider(
        "bridge",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )

    try:
        await provider.refresh_catalog()
        descriptor = provider.describe("configured-model")
    finally:
        await http_client.aclose()

    assert descriptor is not None
    assert descriptor.reasoning_efforts == ("high", "xhigh")


@pytest.mark.parametrize(
    "reasoning_efforts",
    [
        {"": ["high"]},
        {" configured-model": ["high"]},
        {"configured-model": [""]},
        {"configured-model": [" high"]},
        {"configured-model": ["high", "high"]},
    ],
)
def test_bridge_reasoning_effort_fallback_rejects_invalid_values(
    reasoning_efforts: dict[str, list[str]],
) -> None:
    with pytest.raises(ValidationError):
        config(reasoning_efforts=reasoning_efforts)


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
async def test_bridge_catalog_uses_configured_native_endpoints() -> None:
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
async def test_bridge_without_configured_endpoints_has_no_direct_capability() -> None:
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
async def test_bridge_count_tokens_reaches_the_native_endpoint() -> None:
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

    assert seen[0].headers["authorization"] == "Bearer " + provider_config.api_key


def _anthropic_provider(
    seen: list[httpx2.Request],
    **overrides: Any,
) -> tuple[OpenAICompatibleProvider, httpx2.AsyncClient]:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"type": "message", "content": []})

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    provider_config = config(
        models=["native-model"], anthropic_messages_endpoint=True, **overrides
    )
    provider = OpenAICompatibleProvider(
        "opencode",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )
    provider.replace_catalog({"data": [{"id": "native-model"}]})
    return provider, http_client


@pytest.mark.asyncio
async def test_anthropic_messages_authenticates_with_x_api_key() -> None:
    seen: list[httpx2.Request] = []
    provider, http_client = _anthropic_provider(seen)

    try:
        descriptor = provider.describe("native-model")
        assert descriptor is not None
        await provider.send(
            ModelEndpoint.ANTHROPIC_MESSAGES,
            {"model": "native-model", "messages": [], "max_tokens": 16},
            descriptor=descriptor,
        )
    finally:
        await http_client.aclose()

    assert seen[0].headers["x-api-key"] == "test-key"
    assert "authorization" not in seen[0].headers


@pytest.mark.asyncio
async def test_add_header_authorization_sends_bearer_beside_x_api_key() -> None:
    seen: list[httpx2.Request] = []
    provider, http_client = _anthropic_provider(seen, add_header_authorization=True)

    try:
        descriptor = provider.describe("native-model")
        assert descriptor is not None
        await provider.send(
            ModelEndpoint.ANTHROPIC_MESSAGES,
            {"model": "native-model", "messages": [], "max_tokens": 16},
            descriptor=descriptor,
        )
    finally:
        await http_client.aclose()

    assert seen[0].headers["x-api-key"] == "test-key"
    assert seen[0].headers["authorization"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_openai_legs_keep_bearer_and_gain_no_x_api_key() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"id": "resp-1", "object": "response"})

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    provider_config = config(
        models=["native-model"],
        openai_responses_endpoint=True,
        add_header_authorization=True,
    )
    provider = OpenAICompatibleProvider(
        "opencode",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )

    try:
        provider.replace_catalog({"data": [{"id": "native-model"}]})
        descriptor = provider.describe("native-model")
        assert descriptor is not None
        await provider.send(
            ModelEndpoint.OPENAI_RESPONSES,
            {"model": "native-model", "input": "ping"},
            descriptor=descriptor,
        )
    finally:
        await http_client.aclose()

    assert seen[0].headers["authorization"] == "Bearer test-key"
    assert "x-api-key" not in seen[0].headers


@pytest.mark.asyncio
async def test_count_tokens_authenticates_like_the_messages_leg() -> None:
    seen: list[httpx2.Request] = []
    provider, http_client = _anthropic_provider(seen)

    try:
        descriptor = provider.describe("native-model")
        assert descriptor is not None
        await provider.count_tokens(
            {"model": "native-model", "messages": []},
            descriptor=descriptor,
        )
    finally:
        await http_client.aclose()

    assert seen[0].headers["x-api-key"] == "test-key"
    assert "authorization" not in seen[0].headers


@pytest.mark.asyncio
async def test_x_opencode_session_is_absent_unless_enabled() -> None:
    seen: list[httpx2.Request] = []
    provider, http_client = _anthropic_provider(seen)

    try:
        descriptor = provider.describe("native-model")
        assert descriptor is not None
        await provider.send(
            ModelEndpoint.ANTHROPIC_MESSAGES,
            {"model": "native-model", "messages": [], "max_tokens": 16},
            descriptor=descriptor,
            interaction_id="session-42",
        )
    finally:
        await http_client.aclose()

    assert "x-opencode-session" not in seen[0].headers


@pytest.mark.asyncio
async def test_add_header_x_opencode_session_sends_the_interaction_id() -> None:
    seen: list[httpx2.Request] = []
    provider, http_client = _anthropic_provider(
        seen, add_header_x_opencode_session=True
    )

    try:
        descriptor = provider.describe("native-model")
        assert descriptor is not None
        await provider.send(
            ModelEndpoint.ANTHROPIC_MESSAGES,
            {"model": "native-model", "messages": [], "max_tokens": 16},
            descriptor=descriptor,
            interaction_id="session-42",
        )
    finally:
        await http_client.aclose()

    assert seen[0].headers["x-opencode-session"] == "session-42"


@pytest.mark.asyncio
async def test_x_opencode_session_falls_back_to_one_id_per_client() -> None:
    seen: list[httpx2.Request] = []
    provider, http_client = _anthropic_provider(
        seen, add_header_x_opencode_session=True
    )

    try:
        descriptor = provider.describe("native-model")
        assert descriptor is not None
        for _ in range(2):
            await provider.send(
                ModelEndpoint.ANTHROPIC_MESSAGES,
                {"model": "native-model", "messages": [], "max_tokens": 16},
                descriptor=descriptor,
            )
    finally:
        await http_client.aclose()

    sessions = {request.headers["x-opencode-session"] for request in seen}
    assert len(sessions) == 1
    assert sessions.pop()


@pytest.mark.asyncio
async def test_caller_headers_cannot_override_upstream_auth() -> None:
    seen: list[httpx2.Request] = []
    provider, http_client = _anthropic_provider(
        seen, add_header_authorization=True, add_header_x_opencode_session=True
    )

    try:
        descriptor = provider.describe("native-model")
        assert descriptor is not None
        await provider.send(
            ModelEndpoint.ANTHROPIC_MESSAGES,
            {"model": "native-model", "messages": [], "max_tokens": 16},
            descriptor=descriptor,
            interaction_id="session-42",
            extra_headers={
                "x-api-key": "caller",
                "Authorization": "Bearer caller",
                "x-opencode-session": "caller",
                "x-custom": "kept",
            },
        )
    finally:
        await http_client.aclose()

    headers = seen[0].headers
    assert headers["x-api-key"] == "test-key"
    assert headers["authorization"] == "Bearer test-key"
    assert headers["x-opencode-session"] == "session-42"
    assert headers["x-custom"] == "kept"


def write_model_info(tmp_path: Path, models: dict[str, Any]) -> str:
    path = tmp_path / "model-info.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": MODEL_INFO_SCHEMA_VERSION,
                "retrieved_at": datetime.now(UTC).date().isoformat(),
                "models": models,
            }
        ),
        encoding="utf-8",
    )
    return str(path)


def model_info_provider(
    upstream: list[dict[str, Any]],
    **overrides: Any,
) -> tuple[OpenAICompatibleProvider, httpx2.AsyncClient]:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"object": "list", "data": upstream})

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    values: dict[str, Any] = {"models": []}
    values.update(overrides)
    provider_config = config(**values)
    provider = OpenAICompatibleProvider(
        "opencode",
        OpenAICompatibleClient(http_client, provider_config),
        provider_config,
    )
    return provider, http_client


async def catalog_of(provider: OpenAICompatibleProvider) -> list[dict[str, Any]]:
    await provider.refresh_catalog()
    entries = provider.raw_catalog["data"]
    assert isinstance(entries, list)
    return cast(list[dict[str, Any]], entries)


@pytest.mark.asyncio
async def test_model_info_intersects_upstream_ids_with_the_file(tmp_path: Path) -> None:
    """The intersection is the point, and neither side answers it alone.

    Upstream advertises models the file is silent about, and the file names models
    upstream does not serve. What is left is what the operator has both confirmed and
    described — the one set where every row is meaningful.
    """
    path = write_model_info(
        tmp_path,
        {
            "kimi-k3": {"name": "Kimi K3"},
            "file-only": {"name": "File Only"},
        },
    )
    provider, http_client = model_info_provider(
        [{"id": "kimi-k3"}, {"id": "upstream-only"}], model_info_json=path
    )

    try:
        await provider.refresh_catalog()

        assert provider.available_ids == frozenset({"kimi-k3"})
        assert provider.describe("upstream-only") is None
        assert provider.describe("file-only") is None
        assert [entry["id"] for entry in await catalog_of(provider)] == ["kimi-k3"]
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_model_info_describes_a_model_the_upstream_leaves_bare(
    tmp_path: Path,
) -> None:
    """What upstream published stays, and what it omitted arrives from the file."""
    path = write_model_info(
        tmp_path,
        {
            "kimi-k3": {
                "name": "Kimi K3",
                "supported_endpoints": ["/chat/completions", "/v1/messages"],
                "capabilities": {
                    "supports": {"vision": True, "reasoning_effort": ["high"]},
                    "limits": {
                        "max_context_window_tokens": 1_048_576,
                        "max_output_tokens": 131_072,
                    },
                },
                "pricing": {
                    "input": 3.0,
                    "output": 15.0,
                    "cacheRead": 0.3,
                    "cacheWrite": 0.0,
                },
            }
        },
    )
    provider, http_client = model_info_provider(
        [{"id": "kimi-k3", "object": "model", "created": 1_789_000_000}],
        model_info_json=path,
        openai_chat_completions_endpoint=True,
        anthropic_messages_endpoint=True,
    )

    try:
        await provider.refresh_catalog()

        descriptor = provider.describe("kimi-k3")
        assert descriptor is not None
        assert descriptor.endpoints == {
            ModelEndpoint.OPENAI_CHAT_COMPLETIONS,
            ModelEndpoint.ANTHROPIC_MESSAGES,
        }
        assert descriptor.reasoning_efforts == ("high",)
        # No tokenizer was stated, so there is no local admission fact to invent.
        assert descriptor.prompt_token_limits is None

        entry = (await catalog_of(provider))[0]
        assert entry["object"] == "model"
        assert entry["created"] == 1_789_000_000
        assert entry["name"] == "Kimi K3"
        assert entry["pricing"]["cacheRead"] == 0.3
        assert entry["capabilities"]["limits"] == {
            "max_context_window_tokens": 1_048_576,
            "max_output_tokens": 131_072,
        }
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_model_info_endpoints_are_still_intersected_with_the_declared_protocols(
    tmp_path: Path,
) -> None:
    """The file says what a model is served on; the config says what this proxy will send.

    A file claiming the Anthropic leg on an upstream whose operator enabled only
    Responses must not make that leg reachable.
    """
    path = write_model_info(
        tmp_path,
        {"kimi-k3": {"name": "Kimi K3", "supported_endpoints": ["/v1/messages"]}},
    )
    provider, http_client = model_info_provider(
        [{"id": "kimi-k3"}], model_info_json=path, openai_responses_endpoint=True
    )

    try:
        await provider.refresh_catalog()

        descriptor = provider.describe("kimi-k3")
        assert descriptor is not None
        assert descriptor.endpoints == frozenset()
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_a_model_info_entry_without_endpoints_falls_back_to_the_declared_set(
    tmp_path: Path,
) -> None:
    path = write_model_info(tmp_path, {"kimi-k3": {"name": "Kimi K3"}})
    provider, http_client = model_info_provider(
        [{"id": "kimi-k3"}], model_info_json=path, openai_responses_endpoint=True
    )

    try:
        await provider.refresh_catalog()

        descriptor = provider.describe("kimi-k3")
        assert descriptor is not None
        assert descriptor.endpoints == {ModelEndpoint.OPENAI_RESPONSES}
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_a_model_info_entry_with_no_endpoints_at_all_stays_unreachable(
    tmp_path: Path,
) -> None:
    """An explicit empty list is upstream-shaped for "serves nothing", not for "unknown".

    It must not widen into the declared set, which is the same refusal the catalog path
    already makes.
    """
    path = write_model_info(
        tmp_path, {"kimi-k3": {"name": "Kimi K3", "supported_endpoints": []}}
    )
    provider, http_client = model_info_provider(
        [{"id": "kimi-k3"}],
        model_info_json=path,
        openai_responses_endpoint=True,
        anthropic_messages_endpoint=True,
    )

    try:
        await provider.refresh_catalog()

        descriptor = provider.describe("kimi-k3")
        assert descriptor is not None
        assert descriptor.endpoints == frozenset()
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_the_configured_model_allowlist_still_narrows_the_served_catalog(
    tmp_path: Path,
) -> None:
    """`models` and `model_info_json` both narrow, and `/models` reads the result.

    The allowlist used to be applied after the merged entry was already recorded as
    served, which left `/models` advertising a model routing had just dropped.
    """
    path = write_model_info(
        tmp_path,
        {"kimi-k3": {"name": "Kimi K3"}, "glm-5.3": {"name": "GLM 5.3"}},
    )
    provider, http_client = model_info_provider(
        [{"id": "kimi-k3"}, {"id": "glm-5.3"}],
        model_info_json=path,
        models=["kimi-k3"],
    )

    try:
        await provider.refresh_catalog()

        assert provider.available_ids == frozenset({"kimi-k3"})
        assert [entry["id"] for entry in await catalog_of(provider)] == ["kimi-k3"]
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_an_unreadable_model_info_file_fails_at_construction(
    tmp_path: Path,
) -> None:
    """A bad path is a config error, and it must not degrade into a bare catalog.

    Silently carrying on would leave an operator looking at upstream's empty
    descriptions and concluding the file was being used.
    """
    provider_config = config(model_info_json=str(tmp_path / "absent.json"))
    http_client = httpx2.AsyncClient()

    try:
        with pytest.raises(ModelInfoError):
            OpenAICompatibleProvider(
                "opencode",
                OpenAICompatibleClient(http_client, provider_config),
                provider_config,
            )
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_a_refresh_over_an_unchanged_catalog_reports_no_change(
    tmp_path: Path,
) -> None:
    """The merged catalog is what is compared, in both modes.

    Comparing the upstream payload against the merged one would answer "changed" on
    every scheduled refresh whenever a file is configured, because the two are never
    equal.
    """
    path = write_model_info(tmp_path, {"kimi-k3": {"name": "Kimi K3"}})
    provider, http_client = model_info_provider([{"id": "kimi-k3"}], model_info_json=path)

    try:
        assert await provider.refresh_catalog() is True
        assert await provider.refresh_catalog() is False
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_a_configured_file_reports_when_it_was_sampled(tmp_path: Path) -> None:
    """`/api/status` reads this, and a stale sample looks exactly like a current one."""
    path = write_model_info(tmp_path, {"kimi-k3": {"name": "Kimi K3"}})
    provider, http_client = model_info_provider([{"id": "kimi-k3"}], model_info_json=path)

    try:
        freshness = provider.model_info_freshness

        assert freshness is not None
        assert freshness["path"] == path
        assert freshness["age_days"] == 0
        assert freshness["stale"] is False
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_a_bridge_without_a_file_reports_no_provenance(tmp_path: Path) -> None:
    """Absence is `None`, not an empty report: nothing was sampled to have an age."""
    provider, http_client = model_info_provider([{"id": "kimi-k3"}])

    try:
        assert provider.model_info_freshness is None
    finally:
        await http_client.aclose()


def test_model_info_json_is_a_restart_required_setting() -> None:
    assert "model_providers.*.model_info_json" in NOT_HOT_RELOADABLE
    assert "reasoning_efforts" in PROVIDER_NOT_HOT_RELOADABLE["bridge"]
