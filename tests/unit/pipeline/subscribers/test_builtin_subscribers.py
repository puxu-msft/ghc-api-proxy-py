"""Which subscribers are built in, on which event, and in which order.

The point of a registry is that the set and the order are decisions rather than accidents of import order, so this file is where a subscriber added without such a decision fails. It is deliberately blunt: adding one and not updating the expected tuple here is meant to be a failing test, not a passing one that quietly grew an entry.

The two tests at the bottom are the ones that matter most. Everything above them proves `register_builtin_subscribers` does what it says; only those prove anybody calls it, on each of the two paths that reach upstream. A carrier nothing invokes looks identical to a working one from every other angle.
"""

from copy import deepcopy
from typing import Any

import httpx2
import pytest

from app.config.schema import ProxyConfig
from app.model_provider import EndpointNotSupported, ModelDescriptor, ModelEndpoint
from app.models.anthropic import MessagesRequest
from app.pipeline.direct_driver import AnthropicMessagesDriver, RetryBudget
from app.pipeline.direct_driver.base import EVENT_ATTEMPT_PREPARE
from app.pipeline.driver import handle_count_tokens
from app.pipeline.events import SubscriberRegistry
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.subscribers import (
    ANTHROPIC_CACHE_CONTROL_ID,
    ANTHROPIC_THINKING_CAPABILITY_ID,
    ANTHROPIC_TRAILING_ASSISTANT_ID,
    BLANK_TEXT_BLOCKS_ID,
    HOSTED_WEB_SEARCH_GATE_ID,
    SERVER_TOOL_CAPABILITY_ID,
    register_builtin_subscribers,
)
from app.pipeline.subscribers.counting import COUNTING_ONLY
from app.pipeline.translation_driver.registry import TranslatorNotFound, default_registry
from app.pipeline.translation_driver.semantic import TranslationRefused, WebSearchNotExecutable
from app.server.composition import build_chain
from app.tokenization.estimators import estimate_anthropic_input, estimate_responses_input

EXPECTED_ON_ATTEMPT_PREPARE = (
    SERVER_TOOL_CAPABILITY_ID,
    HOSTED_WEB_SEARCH_GATE_ID,
    ANTHROPIC_THINKING_CAPABILITY_ID,
    BLANK_TEXT_BLOCKS_ID,
    ANTHROPIC_TRAILING_ASSISTANT_ID,
    ANTHROPIC_CACHE_CONTROL_ID,
)
# Keyed by event, so a subscriber added on a *different* event fails here too. Asserting one bucket would have let the next one land on `attempt.failed` with both assertions still green — a lock that only covers the door it was hung on.
EXPECTED_BY_EVENT = {EVENT_ATTEMPT_PREPARE: EXPECTED_ON_ATTEMPT_PREPARE}


def frozen_by_event(frozen: Any) -> dict[str, tuple[str, ...]]:
    return {event: frozen.ids(event) for event in frozen.events}


def test_the_built_in_set_is_what_it_is_declared_to_be() -> None:
    registry = SubscriberRegistry[RequestContext]()

    register_builtin_subscribers(registry)

    assert frozen_by_event(registry.freeze()) == EXPECTED_BY_EVENT


def test_a_caller_s_own_subscribers_end_up_in_the_same_registry_as_the_built_ins() -> None:
    """Two registries would mean two frozen orders and no rule about which runs first."""

    async def mine(_: RequestContext) -> None:
        return None

    registry = SubscriberRegistry[RequestContext]()
    registry.subscribe(EVENT_ATTEMPT_PREPARE, "test:mine", mine)

    register_builtin_subscribers(registry)

    assert registry.freeze().ids(EVENT_ATTEMPT_PREPARE) == ("test:mine", *EXPECTED_ON_ATTEMPT_PREPARE)


def test_the_chain_the_server_runs_on_actually_carries_them() -> None:
    config = ProxyConfig.model_validate(
        {"model_providers": {"one": {"type": "github_copilot"}}},
    )
    # Constructing the chain opens no connection, so the client needs no teardown here.
    chain = build_chain(config, http_client=httpx2.AsyncClient())

    assert frozen_by_event(chain.subscribers) == EXPECTED_BY_EVENT


class RecordingProvider:
    """Just enough provider to run the driver loop, keeping what it was actually asked to send."""

    name = "ghc"

    def __init__(self, *, endpoint: ModelEndpoint = ModelEndpoint.ANTHROPIC_MESSAGES) -> None:
        self.sent: list[dict[str, Any]] = []
        self.counted: list[dict[str, Any]] = []
        # The one model's only endpoint. `/responses` is what every GPT model on this upstream advertises and no Claude one does, so the route translates; `/embeddings` has no outbound translator at all, so nothing can carry a Messages body there.
        self._endpoint = endpoint

    @property
    def available_ids(self) -> frozenset[str]:
        return frozenset({"claude-model"})

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
        if model_id != "claude-model":
            return None
        return ModelDescriptor(id=model_id, endpoints=frozenset({self._endpoint}))

    async def refresh_catalog(self) -> bool:
        return False

    async def send(
        self,
        endpoint: ModelEndpoint,
        payload: Any,
        *,
        model_id: str,
        stream: bool = False,
        extra_headers: Any = None,
    ) -> httpx2.Response:
        self.sent.append(dict(payload))
        return httpx2.Response(200)

    async def count_tokens(self, payload: Any, *, model_id: str) -> httpx2.Response:
        # The real provider gates this on the Messages capability and raises `EndpointNotSupported` when it is absent. Mirrored here so a caller that asks anyway fails the same way it would in production, rather than quietly succeeding against a fake that has no opinion.
        if self._endpoint is not ModelEndpoint.ANTHROPIC_MESSAGES:
            raise EndpointNotSupported(self.name, model_id, ModelEndpoint.ANTHROPIC_MESSAGES.value)
        self.counted.append(dict(payload))
        # Carries a request because the caller calls `raise_for_status()`, which needs one. A bare response makes that raise, and the count then quietly falls back to the local estimate — a green assertion about `counted` would have hidden it.
        return httpx2.Response(
            200,
            json={"input_tokens": 7},
            request=httpx2.Request("POST", "https://upstream.invalid/v1/messages/count_tokens"),
        )


async def test_the_driver_never_sends_a_declaration_this_endpoint_cannot_run() -> None:
    """Registration proves the subscriber is in a list. This proves the list is read on the path a request takes.

    Nothing is sent at all now, and that is the point: a request that went out without its only tool would come back answered from memory, under a `Web search results for query:` heading the client attaches whether or not a search happened.
    """
    registry = SubscriberRegistry[RequestContext]()
    register_builtin_subscribers(registry)
    provider = RecordingProvider()
    driver = AnthropicMessagesDriver(provider, registry.freeze(), budget=RetryBudget(max_total=1))
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-model",
        payload={
            "model": "claude-model",
            "messages": [],
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        },
    )
    context.resolved_model = "claude-model"
    context.target_format = WireFormat.ANTHROPIC_MESSAGES

    outcome = await driver.run(context)

    assert provider.sent == []
    assert isinstance(outcome.error, TranslationRefused)

async def test_a_blank_block_is_gone_from_what_the_driver_actually_sends() -> None:
    """The same proof for the second subscriber, because being in the list is not being run.

    The block below is the one production actually sent on 2026-08-20 — a placeholder this proxy synthesised, stored by the client and replayed on its next turn — and upstream refused the whole body over it.

    `original_payload` carries the same body on purpose, and it is not decoration. This conversation ends on an assistant turn, which `builtin:anthropic-trailing-assistant` repairs when *this proxy* is why it ends that way and leaves alone when the client sent it that way. A context built without an original reads as the former and grows a synthetic turn, which would make this assertion about blank blocks fail for a reason that has nothing to do with blank blocks. Saying what the client sent is what keeps the two subscribers from being tested through each other.
    """
    registry = SubscriberRegistry[RequestContext]()
    register_builtin_subscribers(registry)
    provider = RecordingProvider()
    driver = AnthropicMessagesDriver(provider, registry.freeze(), budget=RetryBudget(max_total=1))
    sent_by_client: dict[str, Any] = {
        "model": "claude-model",
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": ""},
                    {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {}},
                ],
            }
        ],
    }
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-model",
        payload=deepcopy(sent_by_client),
        original_payload=sent_by_client,
    )
    context.resolved_model = "claude-model"
    context.target_format = WireFormat.ANTHROPIC_MESSAGES

    await driver.run(context)

    assert provider.sent == [
        {
            "model": "claude-model",
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {}}
                    ],
                }
            ],
        }
    ]


async def test_the_counting_leg_measures_rather_than_refusing() -> None:
    """Counting reports a size; it sends nothing and produces no reply, so nothing can come back invented and there is nothing to refuse for. Refusing would turn a question that has an answer into an error and drop the client onto its local estimate."""
    registry = SubscriberRegistry[RequestContext]()
    register_builtin_subscribers(registry)
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-model",
        payload={
            "model": "claude-model",
            "messages": [],
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        },
    )
    context.resolved_model = "claude-model"
    context.target_format = WireFormat.ANTHROPIC_MESSAGES
    context.extras[COUNTING_ONLY] = True

    for subscription in registry.freeze().for_event(EVENT_ATTEMPT_PREPARE):
        await subscription.handler(context)

    assert context.payload["tools"] == [{"type": "web_search_20250305", "name": "web_search"}]

async def test_a_translated_route_is_counted_from_the_body_it_would_actually_send() -> None:
    """The translated leg is answered properly, not merely answered.

    Two things used to be wrong here. Asking upstream's counter about a Responses route failed the whole request — `provider.count_tokens` gates on the Messages capability and raises `EndpointNotSupported`, a `ProviderError`, which the counting chain propagates rather than degrading. And measuring the Anthropic body described a request that is never sent: `/responses` receives different items, a different tool shape and a different spelling of every role, so its tokenizer counts something else.

    So the count is now taken from the translated body with the estimator for that protocol. The second assertion is what makes the first discriminating: if the two estimators happened to agree on this input, matching one of them would prove nothing about which ran.
    """
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "ghc",
            "model_providers": {"ghc": {"type": "github_copilot"}},
        }
    )
    provider = RecordingProvider(endpoint=ModelEndpoint.OPENAI_RESPONSES)
    chain = build_chain(
        config,
        http_client=httpx2.AsyncClient(),
        providers={"ghc": provider},
    )
    body: dict[str, Any] = {
        "model": "claude-model",
        "system": "be brief",
        "tools": [{"name": "calc", "description": "adds", "input_schema": {"type": "object"}}],
        "messages": [{"role": "user", "content": "what is 2+2?"}],
    }
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-model",
        payload=dict(body),
    )

    answer = await handle_count_tokens(chain, context)

    translated, _ = default_registry(None).translate(
        body, source=WireFormat.ANTHROPIC_MESSAGES, target=WireFormat.OPENAI_RESPONSES
    )
    translated["model"] = "claude-model"
    as_anthropic = estimate_anthropic_input(
        MessagesRequest.model_validate({**body, "max_tokens": 1})
    )
    assert estimate_responses_input(translated) != as_anthropic
    assert answer["input_tokens"] == estimate_responses_input(translated)
    assert answer["estimated"] is True
    # Not called at all, rather than called and refused: a refusal from this one is fatal.
    assert provider.counted == []
    # The trail says why, in words that do not accuse the config file of a fault it does not have.
    assert context.extras["count_tokens_attempts"] == ["ghc:no-counter-for-openai-responses"]


async def test_the_counted_body_is_the_repaired_one() -> None:
    """The count answers about the body that would be sent, so it must go through the same repairs.

    `context_management: {"edits": null}` is the discriminating case, not a blank text block: Claude Code sends it on every request, upstream rejects it outright, and `fix_anthropic_request` is the *only* thing that rewrites it — the `attempt.prepare` subscribers do not touch it. A blank block would have proved nothing here, because `builtin:blank-text-blocks` removes those too and the assertion could not tell which of the two had run.
    """
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "ghc",
            "model_providers": {"ghc": {"type": "github_copilot"}},
        }
    )
    provider = RecordingProvider()
    chain = build_chain(
        config,
        http_client=httpx2.AsyncClient(),
        providers={"ghc": provider},
    )
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-model",
        payload={
            "model": "claude-model",
            "messages": [{"role": "user", "content": "hi"}],
            "context_management": {"edits": None},
        },
    )

    await handle_count_tokens(chain, context)

    [sent] = provider.counted
    assert sent["context_management"] == {"edits": []}


async def test_a_request_no_route_can_carry_is_refused_rather_than_estimated() -> None:
    """The class the old refusal was right about, kept refusing.

    A model whose only endpoint is `/embeddings` has no outbound translator, so `handle()` cannot send it a Messages body at all — the client gets a 400. Answering the count with an estimate would describe a request that is going to be refused, which is the objection the removed `EndpointNotSupported` refusal was written to make. It was right here and wrong about a translated route, so the two are now asked separately.
    """
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "ghc",
            "model_providers": {"ghc": {"type": "github_copilot"}},
        }
    )
    provider = RecordingProvider(endpoint=ModelEndpoint.OPENAI_EMBEDDINGS)
    chain = build_chain(
        config,
        http_client=httpx2.AsyncClient(),
        providers={"ghc": provider},
    )
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-model",
        payload={"model": "claude-model", "messages": [{"role": "user", "content": "hi"}]},
    )

    with pytest.raises(TranslatorNotFound):
        await handle_count_tokens(chain, context)

    assert provider.counted == []


async def test_the_web_search_gate_leaves_the_anthropic_leg_alone() -> None:
    """Its counterpart already owns that leg, and the two must not both act on one request.

    Harmless today by accident rather than by design: `builtin:server-tool-capability` removes both spellings there before this could see them. The route check is what makes it deliberate — without it this reaches a leg whose `tools` is a different protocol's field that happens to share the name.
    """
    from app.pipeline.subscribers import gate_hosted_web_search

    payload: dict[str, Any] = {"tools": [{"type": "web_search"}]}
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-model",
        payload=payload,
        resolved_model="claude-model",
        target_format=WireFormat.ANTHROPIC_MESSAGES,
    )

    await gate_hosted_web_search(context, {})

    assert payload["tools"] == [{"type": "web_search"}]


async def test_a_supported_model_pattern_covers_the_family_it_names() -> None:
    """The entries are regular expressions, so one line claims a version line rather than one model.

    An id list had to be edited every time the catalog gained a model, and the edit is the kind nobody makes until a search has already been answered as failed for a model that could have run it.
    """
    from app.pipeline.subscribers.hosted_web_search import compile_supported, gate_hosted_web_search

    supported = compile_supported([r"gpt-[5-9]\.\d+.*"])
    for model in ("gpt-5.5", "gpt-5.4-mini", "gpt-5.6-sol", "gpt-5.7"):
        context = RequestContext(
            inbound_format=WireFormat.ANTHROPIC_MESSAGES,
            requested_model=model,
            payload={"tools": [{"type": "web_search"}]},
            resolved_model=model,
            target_format=WireFormat.OPENAI_RESPONSES,
        )
        # Returning at all is the assertion: the gate raises for a model it does not recognise.
        await gate_hosted_web_search(context, {"p": supported}, enabled=True, default_provider="p")


async def test_the_feature_is_off_until_someone_turns_it_on() -> None:
    """Default-off, and off refuses even a model every pattern claims.

    The support is real but partial — text where the protocol wants a block pair, citations unread, `max_uses` and the domain lists unsendable — so it is not what every request should get until someone has decided it is.

    Asserted here through the *function's* keyword default — this calls `gate_hosted_web_search` directly, so it does not exercise the schema default at all. That one is guarded by `tests/int/test_pipeline_app.py::test_hosted_web_search_is_off_until_the_config_says_otherwise`, which goes through config and composition. Both defaults have to be off and neither test covers the other.
    """
    from app.pipeline.subscribers.hosted_web_search import compile_supported, gate_hosted_web_search

    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="gpt-5.5",
        payload={"tools": [{"type": "web_search"}]},
        resolved_model="gpt-5.5",
        target_format=WireFormat.OPENAI_RESPONSES,
    )
    with pytest.raises(WebSearchNotExecutable) as refusal:
        await gate_hosted_web_search(context, {"": compile_supported([r"gpt-[5-9]\.\d+.*"])})

    # The two reasons a search does not run must stay distinguishable: an operator reading this has to know whether to turn the feature on or to add a pattern, and the default being off makes
    # "nobody turned it on" the far likelier of the two.
    assert refusal.value.code == "server_tool_disabled"


async def test_the_switch_being_on_does_not_excuse_an_unlisted_model() -> None:
    """Two axes, both of which must hold. On says the feature is offered; the list says which models run it."""
    from app.pipeline.subscribers.hosted_web_search import compile_supported, gate_hosted_web_search

    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-sonnet-5",
        payload={"tools": [{"type": "web_search"}]},
        resolved_model="claude-sonnet-5",
        target_format=WireFormat.OPENAI_RESPONSES,
    )
    with pytest.raises(WebSearchNotExecutable) as refusal:
        await gate_hosted_web_search(
            context, {"": compile_supported([r"gpt-[5-9]\.\d+.*"])}, enabled=True
        )

    assert refusal.value.code == "server_tool_capability_unavailable"


async def test_a_provider_does_not_inherit_another_provider_s_permission() -> None:
    """The key lives under `model_providers.<name>`, so the answer is that provider's alone.

    This was merged into one set across every provider, justified by model ids being unique across the catalog — which answers a different question. Uniqueness of the id says nothing about whether two providers *run* that model the same way, and under the merge a provider whose own list is empty inherited everyone else's: a request routed to it passed a gate its configuration never opened.
    """
    from app.pipeline.subscribers.hosted_web_search import (
        compile_supported_by_provider,
        gate_hosted_web_search,
    )

    supported = compile_supported_by_provider({"a": [], "b": [r"gpt-5\.5"]})
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="gpt-5.5",
        payload={"tools": [{"type": "web_search"}]},
        resolved_model="gpt-5.5",
        target_format=WireFormat.OPENAI_RESPONSES,
    )
    context.provider_name = "a"

    with pytest.raises(WebSearchNotExecutable):
        await gate_hosted_web_search(context, supported, enabled=True)

    # And the provider that did list it is unaffected — otherwise this would pass by refusing everything, which is not the same thing as scoping.
    context.provider_name = "b"
    await gate_hosted_web_search(context, supported, enabled=True)


async def test_an_unknown_provider_refuses_rather_than_falling_back_to_someone_s_list() -> None:
    """Fail closed. A name with no entry gets an empty tuple, not the default provider's permissions."""
    from app.pipeline.subscribers.hosted_web_search import (
        compile_supported_by_provider,
        gate_hosted_web_search,
    )

    supported = compile_supported_by_provider({"known": [r"gpt-5\.5"]})
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="gpt-5.5",
        payload={"tools": [{"type": "web_search"}]},
        resolved_model="gpt-5.5",
        target_format=WireFormat.OPENAI_RESPONSES,
    )
    context.provider_name = "never-configured"

    with pytest.raises(WebSearchNotExecutable):
        await gate_hosted_web_search(
            context, supported, enabled=True, default_provider="known"
        )


async def test_an_entry_is_a_regex_even_when_it_looks_like_a_model_id() -> None:
    """A dot is a wildcard, and model ids here are full of dots.

    Recorded rather than papered over: `gpt-5.5` written as an entry also claims `gpt-5x5`, which would send an unvetted model's search upstream. The escape is `gpt-5\\.5`, and both docstrings that promised a plain id "means what it says" were wrong until this test existed.
    """
    from app.pipeline.subscribers.hosted_web_search import (
        compile_supported_by_provider,
        gate_hosted_web_search,
    )

    def gate_for(pattern: str) -> RequestContext:
        context = RequestContext(
            inbound_format=WireFormat.ANTHROPIC_MESSAGES,
            requested_model="gpt-5x5",
            payload={"tools": [{"type": "web_search"}]},
            resolved_model="gpt-5x5",
            target_format=WireFormat.OPENAI_RESPONSES,
        )
        context.provider_name = "p"
        return context

    unescaped = compile_supported_by_provider({"p": ["gpt-5.5"]})
    # No raise: the unescaped dot matches `x`. This is the behaviour, not the wish.
    await gate_hosted_web_search(gate_for("gpt-5.5"), unescaped, enabled=True)

    escaped = compile_supported_by_provider({"p": [r"gpt-5\.5"]})
    with pytest.raises(WebSearchNotExecutable):
        await gate_hosted_web_search(gate_for(r"gpt-5\.5"), escaped, enabled=True)


async def test_the_counting_leg_measures_rather_than_refusing_on_the_responses_leg_too() -> None:
    """The hosted gate's own exemption, which its sibling's test cannot reach.

    `test_the_counting_leg_measures_rather_than_refusing` targets Anthropic Messages, so this gate returns at its route check before the `COUNTING_ONLY` branch is ever evaluated — delete that branch and the test stays green. Counting a request that translates to Responses is the only shape that exercises it.
    """
    from app.pipeline.subscribers.hosted_web_search import (
        compile_supported_by_provider,
        gate_hosted_web_search,
    )

    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="gpt-model",
        payload={"tools": [{"type": "web_search"}]},
        resolved_model="gpt-model",
        target_format=WireFormat.OPENAI_RESPONSES,
    )
    context.provider_name = "p"
    context.extras[COUNTING_ONLY] = True

    # Off, and the model claimed by nothing: both refusal reasons hold, and counting still returns.
    await gate_hosted_web_search(context, compile_supported_by_provider({"p": []}))

    assert context.payload["tools"] == [{"type": "web_search"}], "counting must not edit the body"


async def test_a_pattern_is_anchored_and_the_dotted_minor_is_required() -> None:
    """Two ways the gate must stay narrow, both of which a looser match would silently widen.

    `gpt-5-mini` is vendor Azure OpenAI — a different supply chain from the `gpt-5.N` line — so a family pattern that did not require the dot would claim a model nobody has put to upstream. And matching is `fullmatch`, so `gpt-5.5-nonsense`-style names are not claimed by an entry written as a plain id: under `search` a list whose whole purpose is to say which models were checked would quietly cover models that were not.
    """
    from app.pipeline.subscribers.hosted_web_search import compile_supported, gate_hosted_web_search

    for pattern, model in ((r"gpt-[5-9]\.\d+.*", "gpt-5-mini"), ("gpt-5.5", "prefix-gpt-5.5")):
        context = RequestContext(
            inbound_format=WireFormat.ANTHROPIC_MESSAGES,
            requested_model=model,
            payload={"tools": [{"type": "web_search"}]},
            resolved_model=model,
            target_format=WireFormat.OPENAI_RESPONSES,
        )
        with pytest.raises(WebSearchNotExecutable):
            await gate_hosted_web_search(context, {"": compile_supported([pattern])}, enabled=True)
