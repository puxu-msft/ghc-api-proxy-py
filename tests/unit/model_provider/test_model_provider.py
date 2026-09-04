from collections.abc import Callable
from dataclasses import replace
from typing import Any

import httpx2
import pytest
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.config.schema import GithubCopilotProviderConfig, ProxyConfig
from app.model_provider import (
    CapabilityMissing,
    DescriptorProviderMismatch,
    EndpointNotSupported,
    GithubCopilotProvider,
    ModelDescriptor,
    ModelEndpoint,
    PromptTokenLimits,
    ProviderNotConfigured,
    ProviderRegistry,
    parse_endpoints,
    parse_prompt_token_limits,
    require_descriptor_owner,
    require_endpoint,
    resolve_default_name,
)
from app.model_provider.ghc_client import GhcApiClient, GhcClientConfig
from app.model_provider.ghc_client.tokens import CopilotTokenManager

BASE_URL = "https://copilot.example"

CATALOG: dict[str, Any] = {
    "object": "list",
    "data": [
        {"id": "claude-model", "supported_endpoints": ["/v1/messages"]},
        {
            "id": "gpt-model",
            "supported_endpoints": ["/responses", "/chat/completions"],
            "capabilities": {
                "tokenizer": "o200k_base",
                "limits": {
                    "max_prompt_tokens": 922_000,
                    "max_context_window_tokens": 1_050_000,
                },
            },
        },
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
    handler: Callable[[httpx2.Request], httpx2.Response],
    *,
    disabled: list[str] | None = None,
) -> tuple[GithubCopilotProvider, httpx2.AsyncClient]:
    def with_token_exchange(request: httpx2.Request) -> httpx2.Response:
        # The real code exchanges the GitHub token for a Copilot one before every authenticated call, so a stand-in that cannot answer this cannot stand in for the real thing.
        if request.url.host == "api.github.com":
            return httpx2.Response(
                200,
                json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
            )
        return handler(request)

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(with_token_exchange))
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
        GhcClientConfig(api_base_url_override=BASE_URL),
        interaction_id="interaction",
    )
    provider = GithubCopilotProvider(
        "ghc",
        client,
        GithubCopilotProviderConfig(type="github_copilot", disabled_models=disabled or []),
        http_client=http_client,
        base_url=BASE_URL,
    )
    provider.replace_catalog(CATALOG)
    return provider, http_client


def descriptor_for(provider: GithubCopilotProvider, model_id: str) -> ModelDescriptor:
    descriptor = provider.describe(model_id)
    assert descriptor is not None
    return descriptor


def upstream(response: httpx2.Response) -> Callable[[httpx2.Request], httpx2.Response]:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "api.github.com":
            return httpx2.Response(
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


def test_prompt_token_limits_are_read_from_the_nested_catalog_shape() -> None:
    limits = parse_prompt_token_limits(CATALOG["data"][1])

    assert limits == PromptTokenLimits(
        tokenizer="o200k_base",
        max_prompt_tokens=922_000,
        max_context_window_tokens=1_050_000,
    )


@pytest.mark.parametrize(
    "capabilities",
    [
        None,
        {"tokenizer": "", "limits": {"max_prompt_tokens": 10, "max_context_window_tokens": 20}},
        {"tokenizer": "o200k_base", "limits": None},
        {"tokenizer": "o200k_base", "limits": {"max_prompt_tokens": True, "max_context_window_tokens": 20}},
        {"tokenizer": "o200k_base", "limits": {"max_prompt_tokens": 10, "max_context_window_tokens": False}},
        {"tokenizer": "o200k_base", "limits": {"max_prompt_tokens": 0, "max_context_window_tokens": 20}},
        {"tokenizer": "o200k_base", "limits": {"max_prompt_tokens": 21, "max_context_window_tokens": 20}},
    ],
)
def test_prompt_token_limits_fail_open_on_incomplete_or_invalid_metadata(
    capabilities: object,
) -> None:
    assert parse_prompt_token_limits({"capabilities": capabilities}) is None


def test_flat_limit_lookalikes_do_not_replace_nested_catalog_metadata() -> None:
    assert (
        parse_prompt_token_limits(
            {
                "tokenizer": "o200k_base",
                "max_prompt_tokens": 922_000,
                "max_context_window_tokens": 1_050_000,
            }
        )
        is None
    )


def test_descriptor_keeps_one_catalog_generation_and_prompt_limit_snapshot() -> None:
    provider, _ = build_provider(upstream(httpx2.Response(200)))
    first = provider.describe("gpt-model")
    assert first is not None

    provider.replace_catalog(CATALOG)
    second = provider.describe("gpt-model")
    assert second is not None

    assert first.provider_name == "ghc"
    assert second.provider_name == "ghc"
    assert first.catalog_generation == 1
    assert second.catalog_generation == 2
    assert first.prompt_token_limits == second.prompt_token_limits == PromptTokenLimits(
        tokenizer="o200k_base",
        max_prompt_tokens=922_000,
        max_context_window_tokens=1_050_000,
    )
    assert first is not second


def test_descriptor_owner_gate_rejects_a_cross_provider_snapshot() -> None:
    descriptor = ModelDescriptor(
        id="gpt-model",
        endpoints=frozenset({ModelEndpoint.OPENAI_RESPONSES}),
        provider_name="first",
    )

    with pytest.raises(DescriptorProviderMismatch):
        require_descriptor_owner(descriptor, "second")


def test_descriptor_owner_gate_accepts_its_issuer() -> None:
    descriptor = ModelDescriptor(
        id="gpt-model",
        endpoints=frozenset({ModelEndpoint.OPENAI_RESPONSES}),
        provider_name="ghc",
    )

    require_descriptor_owner(descriptor, "ghc")


@pytest.mark.asyncio
async def test_primary_provider_send_and_count_reject_foreign_descriptors_before_transport() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if request.url.path.endswith("/count_tokens"):
            return httpx2.Response(200, json={"input_tokens": 1})
        return httpx2.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": "claude-model",
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    provider, http_client = build_provider(handler)
    foreign = replace(
        descriptor_for(provider, "claude-model"),
        provider_name="other",
    )
    try:
        with pytest.raises(DescriptorProviderMismatch):
            await provider.send(
                ModelEndpoint.ANTHROPIC_MESSAGES,
                {"model": "claude-model", "messages": [], "max_tokens": 1},
                descriptor=foreign,
            )
        with pytest.raises(DescriptorProviderMismatch):
            await provider.count_tokens(
                {"model": "claude-model", "messages": []},
                descriptor=foreign,
            )
    finally:
        await http_client.aclose()

    assert seen == []


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
    provider, _ = build_provider(upstream(httpx2.Response(200)), disabled=["banned-model"])
    assert provider.describe("banned-model") is None
    assert "banned-model" not in provider.available_ids
    assert "claude-model" in provider.available_ids


@pytest.mark.asyncio
async def test_inflight_send_uses_the_descriptor_captured_before_catalog_replacement() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"ok": True})

    provider, http_client = build_provider(handler)
    captured = descriptor_for(provider, "claude-model")
    provider.replace_catalog(
        {"data": [{"id": "replacement", "supported_endpoints": ["/responses"]}]}
    )
    try:
        response = await provider.send(
            ModelEndpoint.ANTHROPIC_MESSAGES,
            {"model": "claude-model"},
            descriptor=captured,
        )
    finally:
        await http_client.aclose()

    assert response.status_code == 200
    assert provider.describe("claude-model") is None
    assert captured.catalog_generation == 1
    assert descriptor_for(provider, "replacement").catalog_generation == 2
    assert [str(request.url) for request in seen] == [f"{BASE_URL}/v1/messages"]


@pytest.mark.asyncio
async def test_send_reaches_the_endpoint_the_model_advertises() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "api.github.com":
            return httpx2.Response(
                200,
                json={"token": "copilot", "expires_at": 5000, "refresh_in": 1500},
            )
        seen.append(request)
        return httpx2.Response(200, json={"ok": True})

    provider, http_client = build_provider(handler)
    try:
        await provider.send(
            ModelEndpoint.ANTHROPIC_MESSAGES,
            {"model": "claude-model"},
            descriptor=descriptor_for(provider, "claude-model"),
        )
    finally:
        await http_client.aclose()

    assert [str(request.url) for request in seen] == [f"{BASE_URL}/v1/messages"]


@pytest.mark.asyncio
async def test_unadvertised_endpoint_is_refused_before_the_network() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"ok": True})

    provider, http_client = build_provider(handler)
    try:
        with pytest.raises(EndpointNotSupported):
            await provider.send(
                ModelEndpoint.OPENAI_RESPONSES,
                {"model": "claude-model"},
                descriptor=descriptor_for(provider, "claude-model"),
            )
    finally:
        await http_client.aclose()

    # Fail closed means no request at all, not a request that upstream happens to reject.
    assert seen == []


@pytest.mark.asyncio
async def test_model_with_empty_capabilities_is_refused_before_the_network() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"ok": True})

    provider, http_client = build_provider(handler)
    try:
        with pytest.raises(CapabilityMissing):
            await provider.send(
                ModelEndpoint.ANTHROPIC_MESSAGES,
                {"model": "mute-model"},
                descriptor=descriptor_for(provider, "mute-model"),
            )
    finally:
        await http_client.aclose()

    assert seen == []


@pytest.mark.asyncio
async def test_count_tokens_is_gated_on_the_messages_capability() -> None:
    """Counting a body is refused wherever sending it would be, and before the network.

    Two ways to be refused, and they are not the same: `gpt-model` advertises other endpoints while `mute-model` advertises none. Unknown and disabled ids never produce a routed descriptor, so routing owns those refusals before this provider contract is called.
    """
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"input_tokens": 1})

    provider, http_client = build_provider(handler)
    try:
        with pytest.raises(EndpointNotSupported):
            await provider.count_tokens({"model": "gpt-model"}, descriptor=descriptor_for(provider, "gpt-model"))

        with pytest.raises(CapabilityMissing):
            await provider.count_tokens({"model": "mute-model"}, descriptor=descriptor_for(provider, "mute-model"))
    finally:
        await http_client.aclose()

    assert seen == [], "a refused count must not reach upstream"


@pytest.mark.asyncio
async def test_catalog_refresh_reports_no_change_on_304() -> None:
    responses = [
        httpx2.Response(200, json=CATALOG, headers={"etag": 'W/"v1"'}),
        httpx2.Response(304),
    ]

    def handler(request: httpx2.Request) -> httpx2.Response:
        return responses.pop(0)

    provider, http_client = build_provider(upstream(httpx2.Response(200)))
    try:
        provider._http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))  # pyright: ignore[reportPrivateUsage]
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
    provider, _ = build_provider(upstream(httpx2.Response(200)))
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
    provider, _ = build_provider(upstream(httpx2.Response(200)))
    with pytest.raises(ValueError, match="must be a list"):
        provider.replace_catalog({"data": "nope"})


def test_a_model_that_names_no_endpoints_gets_the_standard_one_for_its_kind() -> None:
    """Copilot omits `supported_endpoints` for part of its catalog — 18 of 42 models on 2026-08-20. A real request to each of them settled which kinds are served: all 14 `chat` on `/chat/completions`, all 3 `embeddings` on `/embeddings`, and the one `completion` on nothing at all.

    This is on the provider rather than only on the report because routing is what has to agree: a report calling a model routable while `require_endpoint` refuses it would be worse than no report.
    """
    provider, _ = build_provider(upstream(httpx2.Response(200)))
    provider.replace_catalog(
        {
            "data": [
                {"id": "embedder", "capabilities": {"type": "embeddings"}},
                {"id": "chatter", "capabilities": {"type": "chat"}},
                {"id": "completer", "capabilities": {"type": "completion"}},
                {"id": "typeless"},
            ]
        }
    )

    def endpoints(model_id: str) -> frozenset[ModelEndpoint]:
        descriptor = provider.describe(model_id)
        assert descriptor is not None
        return descriptor.endpoints

    assert endpoints("embedder") == {ModelEndpoint.OPENAI_EMBEDDINGS}
    assert endpoints("chatter") == {ModelEndpoint.OPENAI_CHAT_COMPLETIONS}
    # Measured 2026-08-20: the live `completion` model answers `model_not_supported` on every endpoint this host serves, so it gets none rather than a guess. Same for a kind nobody has measured at all.
    assert endpoints("completer") == frozenset()
    assert endpoints("typeless") == frozenset()


async def test_a_model_with_an_unstated_endpoint_can_actually_be_sent_to() -> None:
    """The end of the change, not the middle: `require_endpoint` used to refuse these before the network."""
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"ok": True})

    provider, http_client = build_provider(handler)
    provider.replace_catalog({"data": [{"id": "chatter", "capabilities": {"type": "chat"}}]})
    try:
        await provider.send(
            ModelEndpoint.OPENAI_CHAT_COMPLETIONS,
            {"model": "chatter"},
            descriptor=descriptor_for(provider, "chatter"),
        )
    finally:
        await http_client.aclose()

    assert [request.url.path for request in seen] == ["/chat/completions"]


def test_an_endpoint_upstream_did_name_is_never_replaced_by_the_default() -> None:
    """The fallback fires only where upstream was silent.

    The embeddings model has to name something *other* than `/embeddings` to be worth asserting: an embeddings model that named `/embeddings` would read the same whether the value was honoured or overwritten by the default for its kind.
    """
    provider, _ = build_provider(upstream(httpx2.Response(200)))
    provider.replace_catalog(
        {
            "data": [
                {
                    "id": "odd-embedder",
                    "capabilities": {"type": "embeddings"},
                    "supported_endpoints": ["/chat/completions"],
                },
                {"id": "explicitly-none", "supported_endpoints": []},
                {"id": "unreadable", "supported_endpoints": "/responses"},
            ]
        }
    )

    def endpoints(model_id: str) -> frozenset[ModelEndpoint]:
        descriptor = provider.describe(model_id)
        assert descriptor is not None
        return descriptor.endpoints

    assert endpoints("odd-embedder") == {ModelEndpoint.OPENAI_CHAT_COMPLETIONS}
    # Upstream said "none"; that stays a refusal rather than being filled in.
    assert endpoints("explicitly-none") == frozenset()
    # And a field nothing could read must not become a capability either.
    assert endpoints("unreadable") == frozenset()


async def test_an_unreadable_endpoint_field_is_refused_before_the_network() -> None:
    """The end of it: a `supported_endpoints` we could not parse used to be answered by sending to the default.

    The string case is the sharp one — `"/responses"` names a path contradicting the default, so filling it in would have sent the request to `/chat/completions` on the strength of a field nobody could read.
    """
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"ok": True})

    provider, http_client = build_provider(handler)
    provider.replace_catalog(
        {"data": [{"id": "unreadable", "capabilities": {"type": "chat"}, "supported_endpoints": "/responses"}]}
    )
    try:
        with pytest.raises(CapabilityMissing):
            await provider.send(
                ModelEndpoint.OPENAI_CHAT_COMPLETIONS,
                {"model": "unreadable"},
                descriptor=descriptor_for(provider, "unreadable"),
            )
    finally:
        await http_client.aclose()

    assert seen == []


def test_the_catalog_is_kept_as_upstream_sent_it() -> None:
    """The descriptors are a projection built for routing; `raw_catalog` is the original.

    Everything a catalog says beyond the endpoint list — vendor, family, limits, policy state — survives only here, and `debug models` reports on exactly that. Rebuilding it from the descriptors would report a catalog upstream never sent.
    """
    provider, _ = build_provider(upstream(httpx2.Response(200)))

    assert provider.raw_catalog == CATALOG
    assert provider.base_url == BASE_URL


def test_a_rejected_catalog_leaves_the_previous_one_standing() -> None:
    # Fail-closed applies to the report too: a payload that could not be read must not blank out the answer already held.
    provider, _ = build_provider(upstream(httpx2.Response(200)))

    with pytest.raises(ValueError):
        provider.replace_catalog({"data": "nope"})

    assert provider.raw_catalog == CATALOG


def test_send_signature_matches_the_protocol() -> None:
    # Structural check: the concrete provider must satisfy ModelProvider without inheritance.
    from app.model_provider.base import ModelProvider

    provider, _ = build_provider(upstream(httpx2.Response(200)))
    typed: ModelProvider = provider
    assert typed.name == "ghc"


def test_payload_is_not_mutated_by_send_preparation() -> None:
    payload: dict[str, Any] = {"model": "claude-model"}
    before = dict(payload)
    provider, _ = build_provider(upstream(httpx2.Response(200)))
    assert provider.describe("claude-model") is not None
    assert payload == before



@pytest.mark.asyncio
async def test_the_catalog_fetch_is_authenticated() -> None:
    """An unauthenticated catalog request is refused, and the service cannot start without one.

    The headers were held from construction and nothing ever put a token in them, so `/models` went out bare — meaning the service could not start even with valid credentials.
    """
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=CATALOG)

    provider, http_client = build_provider(handler)
    try:
        assert await provider.refresh_catalog() is True
    finally:
        await http_client.aclose()

    catalog_requests = [request for request in seen if request.url.path.endswith("/models")]
    assert catalog_requests, "no catalog request was made"
    assert catalog_requests[-1].headers.get("authorization", "").startswith("Bearer ")


@pytest.mark.asyncio
async def test_each_catalog_refresh_authenticates_afresh() -> None:
    # The Copilot token expires, so headers captured once would authenticate the first refresh and nothing after it. Two refreshes must each ask the token manager.
    asked: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/models"):
            asked.append(request.headers.get("authorization", ""))
            # No etag, so the second refresh is a full fetch rather than a 304.
            return httpx2.Response(200, json=CATALOG)
        return httpx2.Response(200, json={})

    provider, http_client = build_provider(handler)
    try:
        await provider.refresh_catalog()
        await provider.refresh_catalog()
    finally:
        await http_client.aclose()

    assert len(asked) == 2
    assert all(value.startswith("Bearer ") for value in asked)
