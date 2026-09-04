"""A conversation left ending on an assistant turn, and who left it that way.

The 400 is measured — 2026-08-24 against `claude-sonnet-5` through the running proxy, in both content spellings: `This model does not support assistant message prefill. The conversation must end with a user message.`

The two anchor cases below are not hypotheticals either. Each was measured by running this project's own repairs over a legal three-turn body ending in `user` and watching it come out ending in `assistant`. They are written here as end-to-end tests through `handle` rather than as calls to the subscriber, because the thing worth locking is the *interaction*: one pass removes a turn, another has to notice.
"""

from collections.abc import Mapping
from typing import Any

import httpx2

from app.config.schema import ProxyConfig
from app.model_provider import ModelDescriptor, ModelEndpoint
from app.pipeline.driver import handle, handle_count_tokens
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.subscribers.anthropic_trailing_assistant import (
    SYNTHETIC_TEXT,
    repair_trailing_assistant,
)
from app.pipeline.translation_driver.semantic import LossCode
from app.server.composition import build_chain
from app.server.inbound import build_context
from app.server.routes.table import route_for_path

MODEL = ModelDescriptor(
    id="claude-sonnet-5",
    endpoints=frozenset({ModelEndpoint.ANTHROPIC_MESSAGES}),
    reasoning_efforts=("low", "medium", "high", "xhigh", "max"),
    adaptive_thinking=True,
)
SYNTHETIC_TURN = {"role": "user", "content": [{"type": "text", "text": SYNTHETIC_TEXT}]}


async def test_an_emptied_assistant_tail_is_left_alone() -> None:
    """`content: []` is not a prefill, and upstream answers 200 to it — measured here, not assumed.

    `exp/260820-empty-text-probe/` F4 and F6: a final assistant turn with an empty block list answers 200 on this model, and so does one mid-conversation. The shape matters because `drop_blank_text_blocks` *produces* it — that pass empties an assistant turn rather than dropping it — so a flat "must not end on assistant" rule makes the two passes fight, and this one wins by adding a user instruction to a request that already worked.
    """
    provider = RecordingProvider()
    body: dict[str, Any] = {
        "model": "claude-sonnet-5",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "do it"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "  "}]},
            {"role": "user", "content": [{"type": "text", "text": "   "}]},
        ],
    }
    context = context_for(body)

    await handle(chain_for(provider), context)

    [sent] = provider.sent
    assert [m["role"] for m in sent["messages"]] == ["user", "assistant"]
    assert sent["messages"][-1]["content"] == []
    assert "conversion_losses" not in context.extras


async def test_a_body_this_cannot_compare_is_never_given_synthetic_text() -> None:
    """The client's own body is in its own protocol, and a `/responses` one has no `messages` at all.

    Reading `original_payload["messages"]` on that leg returns nothing, and the first draft read nothing as "not the client's" and appended. That put a sentence the client never wrote in front of the model on a path where the client had in fact ended its own conversation on an assistant item.

    Declining leaves a real gap — `drop_blank_text_blocks` runs on translated-to-Anthropic bodies too, so one can still go out unrepaired and earn the 400. That is the direction to fail in: a 400 says exactly what is wrong, a wrong guess reports success.
    """
    context = RequestContext(
        inbound_format=WireFormat.OPENAI_RESPONSES,
        requested_model="claude-sonnet-5",
        payload={
            "model": "claude-sonnet-5",
            "max_tokens": 1024,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "hi"}]},
                {"role": "assistant", "content": [{"type": "text", "text": "there"}]},
            ],
        },
        # What a Responses client actually sent: roles live under `input`, and there is no `messages` key to read.
        original_payload={"model": "claude-sonnet-5", "input": [{"role": "user", "content": "hi"}]},
        target_format=WireFormat.ANTHROPIC_MESSAGES,
    )

    await repair_trailing_assistant(context)

    assert [m["role"] for m in context.payload["messages"]] == ["user", "assistant"]
    assert "conversion_losses" not in context.extras


async def test_the_production_context_builder_keeps_the_original_readable() -> None:
    """The seam every other test here pre-satisfies by hand, exercised through the real builder.

    The discriminator only works because `build_context` deep-copies the working body: `repair_tool_pairs` edits `messages` in place, and under a shallow copy those edits would reach `original_payload` too — the original would then also end on an assistant turn, this module would read it as the client's own prefill, and a body already known to earn a 400 would go out unrepaired. A reviewer mutated that `deepcopy` away and all 30 tests stayed green, because each of them builds its two copies itself.
    """
    provider = RecordingProvider()
    route = route_for_path("/v1/messages")
    assert route is not None
    client_body: dict[str, Any] = {
        "model": "claude-sonnet-5",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "do it"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "done"}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "gone", "content": "42"}]},
        ],
    }
    context = build_context(route, client_body, {}, {})

    await handle(chain_for(provider), context)

    [sent] = provider.sent
    assert sent["messages"][-1] == SYNTHETIC_TURN
    # The original still says what the client said, which is what made the decision above possible.
    assert [m["role"] for m in context.original_payload["messages"]] == ["user", "assistant", "user"]


class RecordingProvider:
    name = "ghc"

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.counted: list[dict[str, Any]] = []

    @property
    def available_ids(self) -> frozenset[str]:
        return frozenset({"claude-sonnet-5"})
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
        return MODEL if model_id == "claude-sonnet-5" else None

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
        self.counted.append(dict(payload))
        return httpx2.Response(
            200,
            json={"input_tokens": 7},
            request=httpx2.Request("POST", "https://upstream.invalid/v1/messages/count_tokens"),
        )


def chain_for(provider: RecordingProvider) -> Any:
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "ghc",
            "model_providers": {"ghc": {"type": "github_copilot"}},
        }
    )
    return build_chain(config, http_client=httpx2.AsyncClient(), providers={"ghc": provider})


def body_with(last_user_content: list[dict[str, Any]]) -> dict[str, Any]:
    """A legal conversation ending on a user turn whose content is about to be taken away."""
    return {
        "model": "claude-sonnet-5",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "do it"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "done"}]},
            {"role": "user", "content": last_user_content},
        ],
    }


def context_for(body: dict[str, Any]) -> RequestContext:
    """Built the way `build_context` builds one, original and working copy kept apart.

    The two copies are the whole point on this path: `original_payload` is what decides whether a trailing assistant turn is the client's own prefill or this proxy's doing, and sharing one dict between them would make every repair look like the client's intent.
    """
    import copy

    return RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-sonnet-5",
        payload=copy.deepcopy(body),
        original_payload=copy.deepcopy(body),
    )


async def test_an_orphaned_tool_result_turn_does_not_leave_the_turn_before_it_trailing() -> None:
    """`repair_tool_pairs` empties and drops that turn — measured — and the conversation ended on the assistant.

    A final user turn holding only `tool_result` blocks whose calls are gone is what a client-side compaction leaves behind, and what this proxy's own thinking-block strip can leave behind. Before this guard the body went out two turns long, ending on `assistant`, and upstream refused the whole request.
    """
    provider = RecordingProvider()
    body = body_with([{"type": "tool_result", "tool_use_id": "toolu_gone", "content": "42"}])

    await handle(chain_for(provider), context_for(body))

    [sent] = provider.sent
    assert [m["role"] for m in sent["messages"]] == ["user", "assistant", "user"]
    assert sent["messages"][-1] == SYNTHETIC_TURN


async def test_a_blank_final_user_turn_does_not_leave_the_turn_before_it_trailing() -> None:
    """The second measured path, through a different pass on a different event.

    `drop_blank_text_blocks` removes a user turn whose only content was whitespace. Kept as its own test rather than parametrised with the one above because the two failures would be diagnosed in different files, and a shared parametrise reports them as one.
    """
    provider = RecordingProvider()
    body = body_with([{"type": "text", "text": "   "}])

    await handle(chain_for(provider), context_for(body))

    [sent] = provider.sent
    assert [m["role"] for m in sent["messages"]] == ["user", "assistant", "user"]
    assert sent["messages"][-1] == SYNTHETIC_TURN


async def test_the_clients_own_prefill_is_left_for_upstream_to_name() -> None:
    """The case this must *not* repair, and the reason it reads `original_payload` at all.

    Prefill is a documented Anthropic feature. A client using it deliberately is asking for something this model no longer offers, and upstream's refusal says precisely that. Appending a turn here would return a perfectly good answer that ignored the constraint the client asked for, and the client would have no way to learn its prefill did nothing.
    """
    provider = RecordingProvider()
    body: dict[str, Any] = {
        "model": "claude-sonnet-5",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "write a haiku"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "Silent"}]},
        ],
    }

    await handle(chain_for(provider), context_for(body))

    [sent] = provider.sent
    assert [m["role"] for m in sent["messages"]] == ["user", "assistant"]


async def test_the_addition_is_recorded_where_the_log_line_reads_it() -> None:
    """A turn the client did not write must not appear in the request silently."""
    provider = RecordingProvider()
    context = context_for(body_with([{"type": "text", "text": "   "}]))

    await handle(chain_for(provider), context)

    losses = context.extras["conversion_losses"]
    assert [loss.code for loss in losses] == [LossCode.SYNTHETIC_TURN_ADDED]


async def test_the_counting_leg_measures_the_repaired_conversation() -> None:
    """A count one turn short of what would be sent measures a different request."""
    provider = RecordingProvider()
    context = context_for(body_with([{"type": "text", "text": "   "}]))

    await handle_count_tokens(chain_for(provider), context)

    [counted] = provider.counted
    assert counted["messages"][-1] == SYNTHETIC_TURN


async def test_a_conversation_already_ending_on_a_user_turn_is_untouched() -> None:
    """The overwhelmingly common shape, and the one an over-eager guard would damage."""
    provider = RecordingProvider()
    body = body_with([{"type": "text", "text": "and now this"}])

    await handle(chain_for(provider), context_for(body))

    [sent] = provider.sent
    assert [m["role"] for m in sent["messages"]] == ["user", "assistant", "user"]
    assert sent["messages"][-1]["content"] == [{"type": "text", "text": "and now this"}]


async def test_running_twice_appends_one_turn() -> None:
    """`attempt.prepare` fires once per attempt, so a retry re-runs this over the payload it already fixed."""
    context = context_for(body_with([{"type": "text", "text": "x"}]))
    context.target_format = WireFormat.ANTHROPIC_MESSAGES
    context.payload["messages"] = context.payload["messages"][:2]

    await repair_trailing_assistant(context)
    await repair_trailing_assistant(context)

    assert [m["role"] for m in context.payload["messages"]] == ["user", "assistant", "user"]


async def test_a_translated_route_is_none_of_this_module_s_business() -> None:
    """The prefill rule belongs to the Anthropic Messages endpoint; a Responses body has its own shape."""
    context = context_for(body_with([{"type": "text", "text": "x"}]))
    context.target_format = WireFormat.OPENAI_RESPONSES
    context.payload["messages"] = context.payload["messages"][:2]

    await repair_trailing_assistant(context)

    assert [m["role"] for m in context.payload["messages"]] == ["user", "assistant"]
