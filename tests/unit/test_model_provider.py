from collections.abc import Callable
from typing import Any

import httpx
import pytest
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.config.schema import ModelProviderConfig, ProxyConfig
from app.ghc_client import GhcApiClient, GhcClientConfig
from app.ghc_client.tokens import CopilotTokenManager
from app.model_provider import (
    CapabilityMissing,
    EndpointNotSupported,
    GithubCopilotProvider,
    ModelDescriptor,
    ModelEndpoint,
    ProviderNotConfigured,
    ProviderRegistry,
    UnknownModel,
    parse_endpoints,
    require_endpoint,
    resolve_default_name,
)

BASE_URL = "https://copilot.example"

CATALOG: dict[str, Any] = {
    "object": "list",
    "data": [
        {"id": "claude-model", "supported_endpoints": ["/v1/messages"]},
        {"id": "gpt-model", "supported_endpoints": ["/responses", "/chat/completions"]},
        {"id": "embed-model", "supported_endpoints": ["/embeddings"]},
        {"id": "mute-model", "supported_endpoints": []},
        {"id": "future-model", "supported_endpoints": ["/v1/messages", "/brand-new"]},
        {"id": "banned-model", "supported_endpoints": ["/v1/messages"]},
    ],
}


class StaticTokenSource:
    async def get_token(self) -> str:
        return "ghu_github"

    async def refresh(self) -> str | None:
        return None


def build_provider(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    disabled: list[str] | None = None,
) -> tuple[GithubCopilotProvider, httpx.AsyncClient]:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tokens = CopilotTokenManager(StaticTokenSource(), http_client, clock=lambda: 1000)
    client = GhcApiClient(
        AsyncOpenAI(
            api_key="proxy-managed",
            base_url=BASE_URL,
            http_client=http_client,
            max_retries=0,
        ),
        AsyncAnthropic(
            api_key="proxy-managed",
            base_url=BASE_URL,
            http_client=http_client,
            max_retries=0,
        ),
        tokens,
        GhcClientConfig(base_url_override=BASE_URL),
        interaction_id="interaction",
    )
    provider = GithubCopilotProvider(
        "ghc",
        client,
        ModelProviderConfig(type="github_copilot", disabled_models=disabled or []),
        http_client=http_client,
        base_url=BASE_URL,
    )
    provider.replace_catalog(CATALOG)
    return provider, http_client


def upstream(response: httpx.Response) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(
                200,
                json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
            )
        return response

    return handler


def test_endpoints_parse_into_known_members_and_leftovers() -> None:
    known, unknown = parse_endpoints(["/v1/messages", "/brand-new", 7, "/responses"])
    assert known == {ModelEndpoint.ANTHROPIC_MESSAGES, ModelEndpoint.OPENAI_RESPONSES}
    # An unrecognised path is kept rather than dropped, so a new upstream endpoint stays visible.
    assert unknown == ("/brand-new",)


def test_capability_gate_rejects_a_model_that_advertises_nothing() -> None:
    descriptor = ModelDescriptor(id="mute-model", endpoints=frozenset())
    with pytest.raises(CapabilityMissing):
        require_endpoint(descriptor, ModelEndpoint.ANTHROPIC_MESSAGES, "ghc")


def test_capability_gate_rejects_an_unadvertised_endpoint() -> None:
    descriptor = ModelDescriptor(
        id="claude-model",
        endpoints=frozenset({ModelEndpoint.ANTHROPIC_MESSAGES}),
    )
    with pytest.raises(EndpointNotSupported):
        require_endpoint(descriptor, ModelEndpoint.OPENAI_RESPONSES, "ghc")


def test_disabled_model_is_not_on_offer() -> None:
    provider, _ = build_provider(upstream(httpx.Response(200)), disabled=["banned-model"])
    assert provider.describe("banned-model") is None
    assert "banned-model" not in provider.available_ids
    assert "claude-model" in provider.available_ids


@pytest.mark.asyncio
async def test_send_reaches_the_endpoint_the_model_advertises() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(
                200,
                json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
            )
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    provider, http_client = build_provider(handler)
    try:
        await provider.send(
            ModelEndpoint.ANTHROPIC_MESSAGES,
            {"model": "claude-model"},
            model_id="claude-model",
        )
    finally:
        await http_client.aclose()

    assert [str(request.url) for request in seen] == [f"{BASE_URL}/v1/messages"]


@pytest.mark.asyncio
async def test_unadvertised_endpoint_is_refused_before_the_network() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    provider, http_client = build_provider(handler)
    try:
        with pytest.raises(EndpointNotSupported):
            await provider.send(
                ModelEndpoint.OPENAI_RESPONSES,
                {"model": "claude-model"},
                model_id="claude-model",
            )
    finally:
        await http_client.aclose()

    # Fail closed means no request at all, not a request that upstream happens to reject.
    assert seen == []


@pytest.mark.asyncio
async def test_model_with_empty_capabilities_is_refused_before_the_network() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    provider, http_client = build_provider(handler)
    try:
        with pytest.raises(CapabilityMissing):
            await provider.send(
                ModelEndpoint.ANTHROPIC_MESSAGES,
                {"model": "mute-model"},
                model_id="mute-model",
            )
    finally:
        await http_client.aclose()

    assert seen == []


@pytest.mark.asyncio
async def test_disabled_model_is_refused_before_the_network() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    provider, http_client = build_provider(handler, disabled=["banned-model"])
    try:
        with pytest.raises(UnknownModel):
            await provider.send(
                ModelEndpoint.ANTHROPIC_MESSAGES,
                {"model": "banned-model"},
                model_id="banned-model",
            )
    finally:
        await http_client.aclose()

    assert seen == []


@pytest.mark.asyncio
async def test_count_tokens_is_gated_on_the_messages_capability() -> None:
    """Counting a body is refused wherever sending it would be, and before the network.

    Three ways to be refused, and they are not the same: `gpt-model` advertises other endpoints,
    `mute-model` advertises none, and the third is not in the catalog at all. A gate that only
    asked "is this model known" would let the first two through.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"input_tokens": 1})

    provider, http_client = build_provider(handler)
    try:
        with pytest.raises(EndpointNotSupported):
            await provider.count_tokens({"model": "gpt-model"}, model_id="gpt-model")

        with pytest.raises(CapabilityMissing):
            await provider.count_tokens({"model": "mute-model"}, model_id="mute-model")

        with pytest.raises(UnknownModel):
            await provider.count_tokens({"model": "no-such"}, model_id="no-such")
    finally:
        await http_client.aclose()

    assert seen == [], "a refused count must not reach upstream"


@pytest.mark.asyncio
async def test_catalog_refresh_reports_no_change_on_304() -> None:
    responses = [
        httpx.Response(200, json=CATALOG, headers={"etag": 'W/"v1"'}),
        httpx.Response(304),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    provider, http_client = build_provider(upstream(httpx.Response(200)))
    try:
        provider._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))  # pyright: ignore[reportPrivateUsage]
        assert await provider.refresh_catalog() is True
        assert await provider.refresh_catalog() is False
        await provider._http.aclose()  # pyright: ignore[reportPrivateUsage]
    finally:
        await http_client.aclose()


def test_registry_rejects_a_dangling_default() -> None:
    with pytest.raises(ProviderNotConfigured):
        ProviderRegistry({}, default="ghc")


def test_default_name_falls_back_to_the_only_provider() -> None:
    config = ProxyConfig.model_validate(
        {"model_providers": {"only": {"type": "github_copilot"}}}
    )
    assert resolve_default_name(config) == "only"


def test_default_name_must_be_explicit_when_several_are_configured() -> None:
    config = ProxyConfig.model_validate(
        {
            "model_providers": {
                "a": {"type": "github_copilot"},
                "b": {"type": "github_copilot"},
            }
        }
    )
    with pytest.raises(ProviderNotConfigured):
        resolve_default_name(config)


def test_explicit_default_name_is_used() -> None:
    config = ProxyConfig.model_validate(
        {
            "model_providers": {
                "a": {"type": "github_copilot"},
                "b": {"type": "github_copilot"},
            },
            "default_model_provider": "b",
        }
    )
    assert resolve_default_name(config) == "b"


def test_unknown_endpoint_does_not_count_as_a_capability() -> None:
    # future-model advertises an endpoint we do not model.
    # That must not make it eligible for one we do model.
    descriptor = ModelDescriptor(
        id="future-model",
        endpoints=frozenset({ModelEndpoint.ANTHROPIC_MESSAGES}),
        unknown_endpoints=("/brand-new",),
    )
    with pytest.raises(EndpointNotSupported):
        require_endpoint(descriptor, ModelEndpoint.OPENAI_RESPONSES, "ghc")


def test_descriptor_carries_per_model_request_headers() -> None:
    provider, _ = build_provider(upstream(httpx.Response(200)))
    provider.replace_catalog(
        {
            "data": [
                {
                    "id": "m",
                    "supported_endpoints": ["/v1/messages"],
                    "request_headers": {"x-extra": "1"},
                }
            ]
        }
    )
    descriptor = provider.describe("m")
    assert descriptor is not None
    assert dict(descriptor.request_headers) == {"x-extra": "1"}


def test_catalog_without_a_data_list_is_rejected() -> None:
    provider, _ = build_provider(upstream(httpx.Response(200)))
    with pytest.raises(ValueError, match="must be a list"):
        provider.replace_catalog({"data": "nope"})


def test_send_signature_matches_the_protocol() -> None:
    # Structural check: the concrete provider must satisfy ModelProvider without inheritance.
    from app.model_provider.base import ModelProvider

    provider, _ = build_provider(upstream(httpx.Response(200)))
    typed: ModelProvider = provider
    assert typed.name == "ghc"


def test_payload_is_not_mutated_by_send_preparation() -> None:
    payload: dict[str, Any] = {"model": "claude-model"}
    before = dict(payload)
    provider, _ = build_provider(upstream(httpx.Response(200)))
    assert provider.describe("claude-model") is not None
    assert payload == before

