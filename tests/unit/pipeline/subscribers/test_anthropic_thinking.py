"""`thinking` and `output_config`, built against the model that will answer.

The shape under test is the one production actually sent on 2026-08-24 and got a 400 for; it is quoted from `rejection_capture`'s file rather than invented, which is why `budget_tokens` is `63999` and `display` is present.

Two of these go through `build_chain` and `handle` rather than calling the subscriber. Being registered is not being run, and on this feature there is a second thing only the full path can prove: the capability the subscriber reads has to travel from the catalog through `decide_route` and `apply_route` onto the context. A test that sets `context.model_descriptor` by hand would stay green if that wiring were cut.
"""

from collections.abc import Mapping
from typing import Any

import httpx2
import pytest

from app.config.schema import ProxyConfig
from app.model_provider import ModelDescriptor, ModelEndpoint
from app.model_provider.types import parse_adaptive_thinking
from app.pipeline.driver import handle, handle_count_tokens
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.subscribers.anthropic_thinking import adapt_thinking_capability
from app.pipeline.translation_driver.reasoning import align_effort
from app.pipeline.translation_driver.semantic import Loss, LossCode
from app.server.composition import build_chain

# The captured body, minus the 380 KB of conversation that came with it.
MEASURED_THINKING: dict[str, Any] = {
    "budget_tokens": 63999,
    "type": "enabled",
    "display": "omitted",
}

ADAPTIVE = ModelDescriptor(
    id="claude-sonnet-5",
    endpoints=frozenset({ModelEndpoint.ANTHROPIC_MESSAGES}),
    reasoning_efforts=("low", "medium", "high", "xhigh", "max"),
    adaptive_thinking=True,
)
# `claude-sonnet-4.5` as the catalog really publishes it: budget limits and no `adaptive_thinking`.
BUDGETED = ModelDescriptor(
    id="claude-sonnet-4.5",
    endpoints=frozenset({ModelEndpoint.ANTHROPIC_MESSAGES}),
    adaptive_thinking=False,
)


def context_for(
    thinking: dict[str, Any] | None,
    *,
    descriptor: ModelDescriptor | None = ADAPTIVE,
    target: WireFormat = WireFormat.ANTHROPIC_MESSAGES,
    extra: dict[str, Any] | None = None,
) -> RequestContext:
    payload: dict[str, Any] = {"model": descriptor.id if descriptor else "unknown", "messages": []}
    if thinking is not None:
        payload["thinking"] = dict(thinking)
    payload.update(extra or {})
    return RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-sonnet-4-5",
        payload=payload,
        resolved_model=descriptor.id if descriptor else "unknown",
        target_format=target,
        model_descriptor=descriptor,
    )


async def test_the_body_that_earned_the_400_goes_out_as_adaptive() -> None:
    """The whole feature, on the one input that is measured rather than imagined."""
    context = context_for(MEASURED_THINKING)

    await adapt_thinking_capability(context, efforts_by_model={})

    assert context.payload["thinking"] == {"type": "adaptive", "display": "omitted"}
    assert "budget_tokens" not in context.payload["thinking"]


async def test_the_dropped_budget_is_recorded_where_the_log_line_reads_it() -> None:
    """A field removed from a request the client wrote must not vanish silently.

    Asserted on `conversion_losses` specifically, not on "some loss exists": that key is the one `observability/request_trace.py` reads, so a loss put anywhere else reaches nobody.
    """
    context = context_for(MEASURED_THINKING)

    await adapt_thinking_capability(context, efforts_by_model={})

    losses = context.extras["conversion_losses"]
    assert [loss.code for loss in losses] == [LossCode.REASONING_INTENT_APPROXIMATED]
    assert "63999" in losses[0].detail


async def test_a_model_without_the_capability_keeps_its_budget() -> None:
    """The rewrite is not "always adaptive". A model with no `adaptive_thinking` *requires* the budget shape, so rewriting it there would break a request that works."""
    context = context_for(MEASURED_THINKING, descriptor=BUDGETED)

    await adapt_thinking_capability(context, efforts_by_model={})

    assert context.payload["thinking"] == MEASURED_THINKING
    assert "conversion_losses" not in context.extras


async def test_a_context_carrying_no_descriptor_falls_back_to_leaving_the_body_alone() -> None:
    """A defensive branch, and this test proves only that — not a system behaviour.

    `decide_route` raises `UnknownModel` the moment `provider.describe()` answers `None`, so no `Route` is built, `apply_route` never runs, and production never reaches the subscriber with `model_descriptor is None`. What can reach it is a hand-built context like this one. The fallback reads as "not adaptive" because that is the branch that leaves a request the client wrote untouched. Spec A-1 records that the reachable question — local refusal versus upstream passthrough for an unknown model — belongs to routing rather than here.
    """
    context = context_for(MEASURED_THINKING, descriptor=None)

    await adapt_thinking_capability(context, efforts_by_model={"unknown": "high"})

    assert context.payload["thinking"] == MEASURED_THINKING
    assert "output_config" not in context.payload


async def test_a_disabled_thinking_is_neither_rewritten_nor_given_an_effort() -> None:
    """`{"type": "disabled"}` is accepted by these models, so there is nothing to repair — and no request asked for the effort that would otherwise be attached."""
    context = context_for({"type": "disabled"})

    await adapt_thinking_capability(context, efforts_by_model={"claude-sonnet-5": "high"})

    assert context.payload["thinking"] == {"type": "disabled"}
    assert "output_config" not in context.payload


async def test_a_translated_route_is_none_of_this_module_s_business() -> None:
    """The check is on the endpoint being spoken to, not on the inbound format: a Responses body has its own reasoning field and this one's `thinking` never reaches the wire."""
    context = context_for(MEASURED_THINKING, target=WireFormat.OPENAI_RESPONSES)

    await adapt_thinking_capability(context, efforts_by_model={"claude-sonnet-5": "high"})

    assert context.payload["thinking"] == MEASURED_THINKING
    assert "output_config" not in context.payload


async def test_an_unconfigured_model_gets_no_output_config_at_all() -> None:
    """Absent means send nothing, which upstream reads as its own default. A fallback value here would put every request on a cost dial nobody set."""
    context = context_for(MEASURED_THINKING)

    await adapt_thinking_capability(context, efforts_by_model={"some-other-model": "max"})

    assert "output_config" not in context.payload


async def test_the_configured_effort_is_keyed_on_the_model_upstream_receives() -> None:
    """The alias the client asked for must not match, and the resolved id must.

    This is the exact trap `strip_denied_beta_flags` fell into: a table keyed on a name that `model_mappings` maps away matches nothing, and the whole feature is inert with no error anywhere. The request shape here is the one that produced it — `claude-sonnet-4-5` mapping to `claude-sonnet-5`.
    """
    by_alias = context_for(MEASURED_THINKING)
    await adapt_thinking_capability(by_alias, efforts_by_model={"claude-sonnet-4-5": "low"})
    assert "output_config" not in by_alias.payload

    by_resolved = context_for(MEASURED_THINKING)
    await adapt_thinking_capability(by_resolved, efforts_by_model={"claude-sonnet-5": "low"})
    assert by_resolved.payload["output_config"] == {"effort": "low"}


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        # Published, and above what the first-party client's hardcoded `low|medium|high` can express — the case that client silently turns into no `output_config` at all.
        ("xhigh", "xhigh"),
        ("max", "max"),
    ],
)
async def test_an_effort_the_catalog_publishes_is_sent_verbatim(
    configured: str, expected: str
) -> None:
    context = context_for(MEASURED_THINKING)

    await adapt_thinking_capability(context, efforts_by_model={"claude-sonnet-5": configured})

    assert context.payload["output_config"] == {"effort": expected}


async def test_an_effort_this_model_does_not_publish_comes_down_to_one_it_does() -> None:
    """Downward, because effort costs money: a request that cannot be met exactly is met with less."""
    narrow = ModelDescriptor(
        id="claude-sonnet-4.6",
        endpoints=frozenset({ModelEndpoint.ANTHROPIC_MESSAGES}),
        reasoning_efforts=("low", "medium", "high", "max"),
        adaptive_thinking=True,
    )
    context = context_for(MEASURED_THINKING, descriptor=narrow)

    await adapt_thinking_capability(context, efforts_by_model={"claude-sonnet-4.6": "xhigh"})

    assert context.payload["output_config"] == {"effort": "high"}


async def test_a_model_publishing_no_efforts_gets_no_output_config() -> None:
    """`None` is the catalog saying nothing, and a guess here is a request asking for something nobody asked for."""
    silent = ModelDescriptor(
        id="claude-sonnet-5",
        endpoints=frozenset({ModelEndpoint.ANTHROPIC_MESSAGES}),
        adaptive_thinking=True,
    )
    context = context_for(MEASURED_THINKING, descriptor=silent)

    await adapt_thinking_capability(context, efforts_by_model={"claude-sonnet-5": "high"})

    assert "output_config" not in context.payload
    # The rewrite still happened; the two decisions are independent.
    assert context.payload["thinking"]["type"] == "adaptive"


async def test_the_client_s_own_output_config_is_not_overwritten() -> None:
    """It used this endpoint's vocabulary to say its own thing; a capability gate does not decide what a request meant."""
    context = context_for(MEASURED_THINKING, extra={"output_config": {"effort": "low"}})

    await adapt_thinking_capability(context, efforts_by_model={"claude-sonnet-5": "max"})

    assert context.payload["output_config"] == {"effort": "low"}


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        ("passthrough", {"type": "adaptive", "display": "omitted"}),
        ("drop", {"type": "adaptive"}),
        ("summarized", {"type": "adaptive", "display": "summarized"}),
    ],
)
async def test_the_display_policy_says_what_happens_to_a_field_the_client_sent(
    policy: Any, expected: dict[str, Any]
) -> None:
    context = context_for(MEASURED_THINKING)

    await adapt_thinking_capability(context, efforts_by_model={}, display=policy)

    assert context.payload["thinking"] == expected


async def test_a_rewriting_display_policy_leaves_a_disabled_thinking_alone() -> None:
    """Asking for a summary of reasoning that will not happen is a body nobody has a reason to send."""
    context = context_for({"type": "disabled"})

    await adapt_thinking_capability(context, efforts_by_model={}, display="summarized")

    assert context.payload["thinking"] == {"type": "disabled"}


async def test_running_twice_changes_nothing_the_second_time() -> None:
    """`attempt.prepare` fires once per attempt and a retry re-runs this over the payload the last pass edited. A second loss recorded there would report a budget dropped twice."""
    context = context_for(MEASURED_THINKING)

    await adapt_thinking_capability(context, efforts_by_model={"claude-sonnet-5": "high"})
    first = dict(context.payload["thinking"])
    await adapt_thinking_capability(context, efforts_by_model={"claude-sonnet-5": "high"})

    assert context.payload["thinking"] == first
    assert len(context.extras["conversion_losses"]) == 1


async def test_a_thinking_present_but_unreadable_stops_everything() -> None:
    """`null`, a string, a number — present and not an object.

    The effort is withheld along with the reshape, and that is the deliberate half: deciding whether to attach one means knowing whether thinking was turned off, and an unreadable field is exactly what does not say.
    """
    for unreadable in ("enabled", None, 7):
        context = context_for(None)
        context.payload["thinking"] = unreadable

        await adapt_thinking_capability(context, efforts_by_model={"claude-sonnet-5": "high"})

        assert context.payload["thinking"] == unreadable
        assert "output_config" not in context.payload


async def test_a_request_that_omits_thinking_still_gets_the_configured_effort() -> None:
    """The two fields are independent, and this is the case the first version got wrong.

    An early return on "no `thinking` object" also skipped the effort, so an operator's `model_thinking_effort` line silently never reached the wire for any request that omitted the field. On `claude-sonnet-5` that is not a request that does no thinking — omitting `thinking` runs adaptive — so there was something for the effort to control the whole time. Measured 2026-08-24: `output_config` alone, on a body carrying no `thinking`, answers 200.
    """
    context = context_for(None)

    await adapt_thinking_capability(context, efforts_by_model={"claude-sonnet-5": "xhigh"})

    assert "thinking" not in context.payload
    assert context.payload["output_config"] == {"effort": "xhigh"}


def test_budget_limits_are_not_evidence_that_budgets_are_accepted() -> None:
    """The catalog entry that makes every other reading of this question wrong.

    `claude-sonnet-5` publishes `min_thinking_budget` and `max_thinking_budget` and *rejects* `budget_tokens`; `claude-sonnet-4.5` publishes the same two and requires it. Only `adaptive_thinking` separates them, so this asserts the parser reads that field and nothing near it.
    """
    sonnet_5 = {
        "capabilities": {
            "supports": {
                "adaptive_thinking": True,
                "min_thinking_budget": 1024,
                "max_thinking_budget": 32000,
            }
        }
    }
    sonnet_4_5 = {
        "capabilities": {"supports": {"min_thinking_budget": 1024, "max_thinking_budget": 32000}}
    }

    assert parse_adaptive_thinking(sonnet_5) is True
    assert parse_adaptive_thinking(sonnet_4_5) is False
    # Not a truthy read: only upstream saying `true` counts, because this bit picks between two mutually exclusive request shapes.
    assert parse_adaptive_thinking({"capabilities": {"supports": {"adaptive_thinking": "yes"}}}) is False
    assert parse_adaptive_thinking({}) is False


async def test_a_body_translated_into_anthropic_shape_is_covered_too() -> None:
    """The judgement is on the endpoint being spoken to, and this is the other half of that.

    Not hypothetical: a `/responses` request naming a Claude model finds no `/responses` on it and routes to Messages instead, and `translation_driver/anthropic_messages.py:_restore_thinking` writes `{"type": "enabled", "budget_tokens": N}` whenever the intent carried a budget. That body reaches this endpoint and earns the same 400. Gating on the inbound format instead of the route would leave it uncovered while every test above stayed green.
    """
    context = RequestContext(
        inbound_format=WireFormat.OPENAI_RESPONSES,
        requested_model="claude-sonnet-5",
        payload={"model": "claude-sonnet-5", "thinking": {"type": "enabled", "budget_tokens": 8000}},
        resolved_model="claude-sonnet-5",
        target_format=WireFormat.ANTHROPIC_MESSAGES,
        model_descriptor=ADAPTIVE,
    )

    await adapt_thinking_capability(context, efforts_by_model={"claude-sonnet-5": "medium"})

    assert context.payload["thinking"] == {"type": "adaptive"}
    assert context.payload["output_config"] == {"effort": "medium"}


async def test_an_effort_name_this_proxy_cannot_rank_is_still_sent_when_published() -> None:
    """The catalog decides membership; `EFFORT_LADDER` only decides order.

    This is the test the suite was missing. Every other effort assertion uses a name that is *also* on the local ladder, so `_at_or_below` returns the same answer and deleting the exact-published branch entirely leaves them green — a reviewer measured exactly that. A published name nobody here can rank is the only input that separates the two branches.
    """
    exotic = ModelDescriptor(
        id="claude-sonnet-5",
        endpoints=frozenset({ModelEndpoint.ANTHROPIC_MESSAGES}),
        reasoning_efforts=("turbo",),
        adaptive_thinking=True,
    )
    context = context_for(MEASURED_THINKING, descriptor=exotic)

    await adapt_thinking_capability(context, efforts_by_model={"claude-sonnet-5": "turbo"})

    assert context.payload["output_config"] == {"effort": "turbo"}


async def test_a_model_publishing_only_unrankable_names_gets_no_effort() -> None:
    """Nothing to compare against, so nothing is chosen — rather than a rung picked out of a hat.

    An unrankable name could be cheaper or far more expensive than what the operator asked for, and there is no way to tell which. Omission here means upstream's own default, which is a real answer.
    """
    exotic = ModelDescriptor(
        id="claude-sonnet-5",
        endpoints=frozenset({ModelEndpoint.ANTHROPIC_MESSAGES}),
        reasoning_efforts=("turbo",),
        adaptive_thinking=True,
    )
    context = context_for(MEASURED_THINKING, descriptor=exotic)

    await adapt_thinking_capability(context, efforts_by_model={"claude-sonnet-5": "max"})

    assert "output_config" not in context.payload


def test_the_reason_does_not_call_a_published_name_no_efforts_at_all() -> None:
    """What the operator is told when their line does nothing, and it used to be false.

    `align_effort('max', ('turbo',))` reported "this model advertises no reasoning efforts" — about a model that advertises one. An operator reading that goes looking for a catalog problem instead of at the only thing they can act on, which is that `turbo` is the name on offer.
    """
    resolution = align_effort("max", ("turbo",))

    assert resolution.effort is None
    assert "turbo" in resolution.reason
    assert "no reasoning efforts" not in resolution.reason


class CapableProvider:
    """A provider whose catalog answer carries the capability, so routing has something to carry."""

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
        return ADAPTIVE if model_id == "claude-sonnet-5" else None

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
        self.counted.append(dict(payload))
        # Carries a request because the caller calls `raise_for_status()`, which needs one. Without it the count quietly falls back to the local estimate and an assertion about `counted` would still be green while nothing upstream was ever asked.
        return httpx2.Response(
            200,
            json={"input_tokens": 7},
            request=httpx2.Request("POST", "https://upstream.invalid/v1/messages/count_tokens"),
        )


async def test_the_capability_reaches_the_wire_through_routing_and_the_chain() -> None:
    """End to end on the path the failing request took, including the alias it arrived under.

    This is the only test here that would fail if `decide_route` stopped putting the descriptor on the `Route`, or `apply_route` stopped copying it onto the context, or nobody registered the subscriber. Every assertion above sets the descriptor by hand and would sail through all three.
    """
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "ghc",
            "model_providers": {"ghc": {"type": "github_copilot"}},
            "model_mappings": {"claude-sonnet-4-5": "claude-sonnet-5"},
            "model_thinking_effort": {"claude-sonnet-5": "xhigh"},
        }
    )
    provider = CapableProvider()
    chain = build_chain(config, http_client=httpx2.AsyncClient(), providers={"ghc": provider})
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-sonnet-4-5",
        payload={
            "model": "claude-sonnet-4-5",
            "max_tokens": 64000,
            "messages": [{"role": "user", "content": "hi"}],
            "thinking": dict(MEASURED_THINKING),
        },
    )

    await handle(chain, context)

    [sent] = provider.sent
    assert sent["model"] == "claude-sonnet-5"
    assert sent["thinking"] == {"type": "adaptive", "display": "omitted"}
    assert sent["output_config"] == {"effort": "xhigh"}
    assert isinstance(context.extras["conversion_losses"][0], Loss)


def chain_for(provider: CapableProvider) -> Any:
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "ghc",
            "model_providers": {"ghc": {"type": "github_copilot"}},
            "model_mappings": {"claude-sonnet-4-5": "claude-sonnet-5"},
            "model_thinking_effort": {"claude-sonnet-5": "xhigh"},
        }
    )
    return build_chain(config, http_client=httpx2.AsyncClient(), providers={"ghc": provider})


async def test_a_request_omitting_thinking_carries_the_effort_all_the_way_to_the_wire() -> None:
    """The unit assertion for this case says the subscriber does it; this says nothing upstream of it undoes it.

    Kept separate from the reshape seam above because the two fail differently: that one dies if the descriptor stops travelling, this one dies if the effort branch ever ends up behind a `thinking` check again.
    """
    provider = CapableProvider()
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-sonnet-4-5",
        payload={
            "model": "claude-sonnet-4-5",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    await handle(chain_for(provider), context)

    [sent] = provider.sent
    assert "thinking" not in sent
    assert sent["output_config"] == {"effort": "xhigh"}


async def test_the_counting_leg_measures_the_body_that_would_actually_be_sent() -> None:
    """Counting has to see the same reshape generation does, and only this path can prove it.

    A reviewer measured the gap: adding `if context.extras.get(COUNTING_ONLY): return` to this subscriber left all 39 tests across both subscriber files green, because none of them reached `handle_count_tokens` with a body this module would touch. Under that mutation the count would go out carrying `enabled` and a budget while the real request went out as adaptive — two answers to "what does this request look like", which is the one thing `handle_count_tokens` exists to prevent.
    """
    provider = CapableProvider()
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-sonnet-4-5",
        payload={
            "model": "claude-sonnet-4-5",
            "max_tokens": 64000,
            "messages": [{"role": "user", "content": "hi"}],
            "thinking": dict(MEASURED_THINKING),
        },
    )

    answer = await handle_count_tokens(chain_for(provider), context)

    assert answer == {"input_tokens": 7}
    [counted] = provider.counted
    assert counted["thinking"] == {"type": "adaptive", "display": "omitted"}
    assert "budget_tokens" not in counted["thinking"]
    assert counted["output_config"] == {"effort": "xhigh"}
    # One attempt, one loss. A count that recorded the dropped budget twice would be reporting a request that was reshaped twice.
    assert len(context.extras["conversion_losses"]) == 1
