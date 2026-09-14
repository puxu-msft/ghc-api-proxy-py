from collections.abc import Mapping
from typing import Any

import httpx2

from app.config.schema import ProxyConfig
from app.model_provider import ModelDescriptor, ModelEndpoint, ProviderRegistry
from app.pipeline.driver import shape_request
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.routing import decide_route, translation_target
from app.pipeline.translation_driver.registry import default_registry
from app.server.composition import build_chain


class _Provider:
    name: str
    base_url: str
    catalog_refreshed_at: str
    raw_catalog: Mapping[str, Any]
    available_ids: frozenset[str]
    disabled_ids: frozenset[str]

    def __init__(self) -> None:
        self.name = "cc"
        self.base_url = "https://api.commandcode.ai"
        self.catalog_refreshed_at = "now"
        self.raw_catalog = {"object": "list", "data": []}
        self.available_ids = frozenset({"m"})
        self.disabled_ids = frozenset()

    def describe(self, model_id: str) -> ModelDescriptor | None:
        if model_id != "m":
            return None
        return ModelDescriptor(
            id="m",
            endpoints=frozenset({ModelEndpoint.COMMANDCODE_GENERATE}),
            provider_name="cc",
            catalog_generation=1,
            catalog_refreshed_at="now",
        )

    async def refresh_catalog(self) -> bool:
        return False

    async def send(
        self,
        endpoint: ModelEndpoint,
        payload: Mapping[str, Any],
        *,
        descriptor: ModelDescriptor,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
        interaction_id: str | None = None,
    ) -> httpx2.Response:
        del endpoint, payload, descriptor, stream, extra_headers, interaction_id
        raise AssertionError("routing test must not send")

    async def count_tokens(
        self,
        payload: Mapping[str, Any],
        *,
        descriptor: ModelDescriptor,
    ) -> httpx2.Response:
        del payload, descriptor
        raise AssertionError("routing test must not count")


def test_commandcode_is_selected_as_a_distinct_translated_target() -> None:
    providers = ProviderRegistry({"cc": _Provider()}, default="cc")

    for inbound in (
        WireFormat.ANTHROPIC_MESSAGES,
        WireFormat.OPENAI_RESPONSES,
        WireFormat.OPENAI_CHAT_COMPLETIONS,
    ):
        route = decide_route(
            requested_model="m",
            inbound_format=inbound,
            providers=providers,
            mappings={},
        )
        assert route.endpoint is ModelEndpoint.COMMANDCODE_GENERATE
        assert route.target_format is WireFormat.COMMANDCODE
        assert route.translation_required is True


def test_commandcode_writer_receives_the_resolved_model_after_mapping() -> None:
    providers = ProviderRegistry({"cc": _Provider()}, default="cc")
    route = decide_route(
        requested_model="alias",
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        providers=providers,
        mappings={"alias": "m"},
    )
    assert route.descriptor is not None

    body, _ = default_registry().translate(
        {
            "model": "alias",
            "messages": [{"role": "user", "content": "hello"}],
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.COMMANDCODE,
        target_model=translation_target(route.descriptor, ()),
    )

    assert body["params"]["model"] == "m"


def test_translated_commandcode_request_extracts_zdr_after_general_header_policy() -> None:
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "cc",
            "model_providers": {
                "cc": {
                    "type": "commandcode",
                    "api_key": "user_test",
                    "models": ["m"],
                }
            },
        }
    )
    chain = build_chain(
        config,
        http_client=httpx2.AsyncClient(),
        providers={"cc": _Provider()},
    )
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="m",
        payload={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        client_headers={
            "x-cmd-zdr": "1",
            "anthropic-beta": "client-only",
        },
    )

    shape_request(chain, context)

    assert context.client_headers == {}
    assert context.commandcode_zdr is True
