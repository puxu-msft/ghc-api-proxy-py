"""Which subscribers are built in, on which event, and in which order.

The point of a registry is that the set and the order are decisions rather than accidents of import order, so this file is where a subscriber added without such a decision fails. It is deliberately blunt: adding one and not updating the expected tuple here is meant to be a failing test, not a passing one that quietly grew an entry.

The two tests at the bottom are the ones that matter most. Everything above them proves `register_builtin_subscribers` does what it says; only those prove anybody calls it, on each of the two paths that reach upstream. A carrier nothing invokes looks identical to a working one from every other angle.
"""

from typing import Any

import httpx

from app.config.schema import ProxyConfig
from app.model_provider import ModelDescriptor, ModelEndpoint
from app.pipeline.direct_driver import AnthropicMessagesDriver, RetryBudget
from app.pipeline.direct_driver.base import EVENT_ATTEMPT_PREPARE
from app.pipeline.events import SubscriberRegistry
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.subscribers import (
    BLANK_TEXT_BLOCKS_ID,
    SERVER_TOOL_CAPABILITY_ID,
    register_builtin_subscribers,
)
from app.server.composition import build_chain
from app.server.handler import handle_count_tokens

EXPECTED_ON_ATTEMPT_PREPARE = (SERVER_TOOL_CAPABILITY_ID, BLANK_TEXT_BLOCKS_ID)
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
    chain = build_chain(config, http_client=httpx.AsyncClient())

    assert frozen_by_event(chain.subscribers) == EXPECTED_BY_EVENT


class RecordingProvider:
    """Just enough provider to run the driver loop, keeping what it was actually asked to send."""

    name = "ghc"

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.counted: list[dict[str, Any]] = []

    @property
    def available_ids(self) -> frozenset[str]:
        return frozenset({"claude-model"})

    def describe(self, model_id: str) -> ModelDescriptor | None:
        if model_id != "claude-model":
            return None
        return ModelDescriptor(id=model_id, endpoints=frozenset({ModelEndpoint.ANTHROPIC_MESSAGES}))

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
    ) -> httpx.Response:
        self.sent.append(dict(payload))
        return httpx.Response(200)

    async def count_tokens(self, payload: Any, *, model_id: str) -> httpx.Response:
        self.counted.append(dict(payload))
        # Carries a request because the caller calls `raise_for_status()`, which needs one. A bare response makes that raise, and the count then quietly falls back to the local estimate — a green assertion about `counted` would have hidden it.
        return httpx.Response(
            200,
            json={"input_tokens": 7},
            request=httpx.Request("POST", "https://upstream.invalid/v1/messages/count_tokens"),
        )


async def test_the_declaration_is_gone_from_what_the_driver_actually_sends() -> None:
    """The one assertion that would survive the carrier being wired to nothing being noticed late.

    Registration proves the subscriber is in a list. This proves the list is read on the path a request takes, and that what upstream receives is the edited payload rather than the copy the attempt opened with.
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

    await driver.run(context)

    assert provider.sent == [{"model": "claude-model", "messages": []}]


async def test_a_blank_block_is_gone_from_what_the_driver_actually_sends() -> None:
    """The same proof for the second subscriber, because being in the list is not being run.

    The block below is the one production actually sent on 2026-08-20 — a placeholder this proxy synthesised, stored by the client and replayed on its next turn — and upstream refused the whole body over it.
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
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": ""},
                        {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {}},
                    ],
                }
            ],
        },
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


async def test_the_counting_leg_gets_the_same_treatment_as_the_leg_it_measures() -> None:
    """Upstream rejects a counting request over a server tool in the very same words.

    Measured 2026-08-20: `/v1/messages/count_tokens` with a `web_search_20250305` declaration answers `The use of the web search tool is not supported.` / `unsupported_value`, character for character what `/v1/messages` answers, while the same body without tools and the same body with an ordinary function tool both return a count. So this path has to run the subscribers too, and a count taken before they ran would have measured a body that was never going to be sent.
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
        http_client=httpx.AsyncClient(),
        providers={"ghc": provider},
    )
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-model",
        payload={
            "model": "claude-model",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        },
    )

    answer = await handle_count_tokens(chain, context)

    assert answer == {"input_tokens": 7}
    assert provider.counted == [
        {"model": "claude-model", "messages": [{"role": "user", "content": "hi"}]}
    ]
