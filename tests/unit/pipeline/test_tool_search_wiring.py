"""The chain that carries the search tool's name from the request half to the response half.

Every other test in this area injects the name at the layer it is testing — `translate_response(client_search_tool=...)`, `ResponsesAssembler(client_search_tool=...)`. That proves each consumer works and proves **nothing** about whether anything ever supplies them: a review deleted the three lines in `driver.py` that write the name onto the context and all 1809 tests stayed green.

So these go through `handle()` and `assembler_for()`, which is where the name is actually produced and read. Without them the feature can be disconnected silently, which is the exact shape this project has a standing lesson about.
"""

from collections.abc import Mapping
from typing import Any

import httpx2

from app.config.schema import ProxyConfig
from app.model_provider import ModelDescriptor, ModelEndpoint
from app.pipeline.delivery_policy import assembler_for
from app.pipeline.driver import CLIENT_SEARCH_TOOL, handle
from app.pipeline.request import RequestContext, WireFormat
from app.server.composition import build_chain

SEARCH_TOOL: dict[str, Any] = {
    "name": "ToolSearch",
    "description": "Fetches full schema definitions for deferred tools so they can be called.",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
}
DEFERRED: dict[str, Any] = {
    "name": "get_weather",
    "description": "Get the weather.",
    "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
    "defer_loading": True,
}

RESPONSES_MODEL = ModelDescriptor(
    id="gpt-5.6-sol",
    endpoints=frozenset({ModelEndpoint.OPENAI_RESPONSES}),
    provider_name="ghc",
)


class ResponsesProvider:
    """A provider whose only model answers on the Responses endpoint, so routing translates."""

    name = "ghc"

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    @property
    def available_ids(self) -> frozenset[str]:
        return frozenset({"gpt-5.6-sol"})
    @property
    def raw_catalog(self) -> Mapping[str, Any]:
        return {}


    # Reporting-only members of the provider protocol, here so this stub satisfies it. Nothing on this test's path reads them; `/api/status` does.
    @property
    def disabled_ids(self) -> frozenset[str]:
        return frozenset()

    @property
    def base_url(self) -> str:
        return "https://stub.invalid"

    @property
    def catalog_refreshed_at(self) -> str:
        return "2026-08-27T00:00:00+00:00"

    def describe(self, model_id: str) -> ModelDescriptor | None:
        return RESPONSES_MODEL if model_id == "gpt-5.6-sol" else None

    async def refresh_catalog(self) -> bool:
        return False

    async def send(
        self,
        endpoint: ModelEndpoint,
        payload: Any,
        *,
        descriptor: ModelDescriptor,
        stream: bool = False,
        extra_headers: Any = None,
    ) -> httpx2.Response:
        self.sent.append(dict(payload))
        return httpx2.Response(200)

    async def count_tokens(self, payload: Any, *, descriptor: ModelDescriptor) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={"input_tokens": 7},
            request=httpx2.Request("POST", "https://upstream.invalid/v1/messages/count_tokens"),
        )


def chain_and_context() -> tuple[Any, RequestContext, ResponsesProvider]:
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "ghc",
            "model_providers": {"ghc": {"type": "github_copilot"}},
            "model_mappings": {"gpt": "gpt-5.6-sol"},
        }
    )
    provider = ResponsesProvider()
    chain = build_chain(config, http_client=httpx2.AsyncClient(), providers={"ghc": provider})
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="gpt",
        payload={
            "model": "gpt",
            "max_tokens": 64,
            "tools": [SEARCH_TOOL, DEFERRED],
            "messages": [{"role": "user", "content": "What is the weather in Paris?"}],
        },
    )
    return chain, context, provider


async def test_handling_a_request_puts_the_search_tools_name_on_the_context() -> None:
    """The producing end of the chain, exercised through the real entry point.

    Also checks the translation actually happened on the way — a name recorded beside a body that was never promoted would be worse than no name at all.
    """
    chain, context, provider = chain_and_context()

    await handle(chain, context)

    assert context.extras[CLIENT_SEARCH_TOOL] == "ToolSearch"
    [sent] = provider.sent
    assert any(tool.get("type") == "tool_search" for tool in sent["tools"])


async def test_the_streaming_assembler_is_built_with_the_name_the_request_recorded() -> None:
    """The consuming end, through `assembler_for` rather than by constructing the assembler by hand.

    This is the seam a mutation could cut without any other test noticing: `assembler_for` reading a different key, or not reading one at all, leaves every assembler unit test green while the streamed search request reaches the client as an empty text block.
    """
    chain, context, _ = chain_and_context()
    handled = await handle(chain, context)

    assembler = assembler_for(handled)

    assert getattr(assembler, "_client_search_tool", None) == "ToolSearch"


async def test_a_request_with_no_search_records_no_name() -> None:
    """The negative half: an ordinary request must not leave a stale name behind for the response side."""
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "ghc",
            "model_providers": {"ghc": {"type": "github_copilot"}},
            "model_mappings": {"gpt": "gpt-5.6-sol"},
        }
    )
    provider = ResponsesProvider()
    chain = build_chain(config, http_client=httpx2.AsyncClient(), providers={"ghc": provider})
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="gpt",
        payload={
            "model": "gpt",
            "max_tokens": 64,
            "tools": [{"name": "Read", "input_schema": {"type": "object"}}],
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    await handle(chain, context)

    assert CLIENT_SEARCH_TOOL not in context.extras
