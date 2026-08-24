"""`thinking` and `output_config`, built for the model that is actually going to answer.

Copilot serves two generations of Claude on the same Anthropic Messages endpoint and they take mutually exclusive spellings of the same request. A model that publishes `capabilities.supports.adaptive_thinking` **rejects** `thinking: {"type": "enabled", "budget_tokens": N}` outright; one that does not publish it **requires** that shape. There is no body that satisfies both, so the body has to be chosen against the catalog.

Measured, on the primary path. 2026-08-24, `req=530e0e10-c724-45a0-964a-129c3351646a`: a Claude Code request naming `claude-sonnet-4-5`, mapped by `model_mappings` to `claude-sonnet-5`, went out with `{"budget_tokens": 63999, "type": "enabled", "display": "omitted"}` and came back `"thinking.type.enabled" is not supported for this model. Use "thinking.type.adaptive" and "output_config.effort" to control thinking behavior.` The outbound body is on disk — `rejection_capture` kept it — which is why the shape above is quoted rather than reconstructed.

**Proactive, never reactive.** The alternative is to let the 400 happen, learn from it and retry, which is what `copilot-api-js` does. It is rejected here for a reason that costs nothing to honour: `docs/.human-controlled/upstream-retry-and-continuation.md:9` lists 400 among the things this proxy cannot continue from. Building the request correctly in the first place never raises that question, and it is also what the first-party client does.

**Why the budget does not become the effort.** It is tempting, and this project already has a budget-to-effort ladder for the Responses leg. It is wrong here: the budget in that measured request is exactly `max_tokens - 1`, a number derived from a size limit rather than a statement about depth. Reading it as a cost dial invents a signal the client never sent — and lands every Claude Code turn on `max`. **The user ruled on 2026-08-24**: not derived from `budget_tokens`, but from a new `model_thinking_effort` mapping, per model, aligned against what the catalog publishes.

**What follows from that ruling rather than being part of it**: an unset model gets no `output_config` at all. That is this module's own derivation — a per-model mapping has no value for a model nobody keyed, and inventing a global default would put every request on a dial nobody set. It is recorded as a derived rule in the spec's §4.2, revisable on review consensus, and must not be cited as something the user closed.

Spec: `.dev/docs/anthropic-direct-request-shape/spec.md`.
"""

import logging
from collections.abc import Mapping
from typing import Any, cast

from app.config.schema import ThinkingDisplayPolicy
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.translation_driver.reasoning import align_effort
from app.pipeline.translation_driver.semantic import Loss, LossCode

logger = logging.getLogger(__name__)

SUBSCRIBER_ID = "builtin:anthropic-thinking-capability"

# Where the request half of a crossing leaves what it could not carry. Written by the translation drivers on the translated legs and by nothing at all on this one until now, which is the whole reason a dropped `budget_tokens` needs to be put here rather than only logged: `observability/request_trace.py` reads this key, so a loss recorded here reaches the console line and the record, and a loss recorded anywhere else reaches nobody.
_REQUEST_LOSSES = "conversion_losses"


def _record_loss(context: RequestContext, detail: str) -> None:
    recorded = context.extras.get(_REQUEST_LOSSES)
    if not isinstance(recorded, list):
        recorded = []
        context.extras[_REQUEST_LOSSES] = recorded
    cast(list[Any], recorded).append(Loss(LossCode.REASONING_INTENT_APPROXIMATED, detail))


def _apply_display(thinking: dict[str, Any], policy: ThinkingDisplayPolicy, *, kind: object) -> None:
    """Put `thinking.display` where the operator asked for it.

    `drop` is unconditional; the two rewriting values are not applied to a disabled `thinking`, where asking for a summary of reasoning that will not happen is a body nobody has any reason to send. `passthrough` — the default — adds nothing and removes nothing, so a client that said `display` keeps saying it and one that said nothing stays silent.
    """
    if policy == "passthrough":
        return
    if policy == "drop":
        thinking.pop("display", None)
        return
    if kind != "disabled":
        thinking["display"] = policy


def _aligned_effort(context: RequestContext, configured: str) -> str | None:
    """The configured effort, fitted to what this model publishes, or `None` to send nothing."""
    descriptor = context.model_descriptor
    resolution = align_effort(configured, descriptor.reasoning_efforts if descriptor else None)
    if resolution.effort is None:
        # INFO rather than debug: an operator who wrote a line in `model_thinking_effort` and gets no `output_config` on the wire is looking at a setting that silently does nothing, and the reason is the one thing that tells them whether to fix the config or leave it alone.
        logger.info(
            "not sending output_config.effort for %r: %s",
            context.resolved_model,
            resolution.reason,
        )
        return None
    if resolution.approximated:
        logger.info(
            "output_config.effort for %r: %s", context.resolved_model, resolution.reason
        )
    return resolution.effort


async def adapt_thinking_capability(
    context: RequestContext,
    *,
    efforts_by_model: Mapping[str, str],
    display: ThinkingDisplayPolicy = "passthrough",
) -> None:
    """Reshape `thinking` for the target model and attach the effort the operator asked for.

    Reads the route rather than the inbound format, for the reason its sibling `adapt_server_tools` gives: what upstream accepts is a property of the endpoint being spoken to, so a request translated *into* Anthropic shape belongs here too and one translated *out* of it does not.

    **Two independent steps, and the order between them is the only thing they share.** `thinking` and `output_config` are separate top-level fields that upstream reads separately — measured 2026-08-24, `output_config` alone on a request carrying no `thinking` at all answers 200. Running them as one pass is how the first version got this wrong: an early return on "no `thinking` object" also skipped the effort, so an operator's `model_thinking_effort` line silently never reached the wire for any request that omitted `thinking` — which on `claude-sonnet-5` is not a request that does no thinking, because omitting the field runs adaptive.

    **Not exempt on the counting leg.** Nothing here refuses anything or invents a reply — it is a reshape, and a count taken from a body that skipped it would measure a request nobody was going to send. `output_config` is small, but `budget_tokens` disappearing is not nothing, and the two legs disagreeing about what the body looks like is exactly what `handle_count_tokens` exists to avoid.

    Idempotent, which matters because `attempt.prepare` fires once per attempt and a retry re-runs it over the payload the last pass already edited: a `thinking` this has rewritten reads as `adaptive`, which is the passthrough branch, so no second loss is recorded and no field moves twice.
    """
    if context.target_format is not WireFormat.ANTHROPIC_MESSAGES:
        return
    payload = context.payload
    thinking = payload.get("thinking")

    if "thinking" in payload and not isinstance(thinking, dict):
        # Present but not an object this can read — `null`, a string, a number. Left whole for upstream to name, and the effort is left alone with it: deciding whether to attach one means knowing whether thinking was turned off, and that is exactly what an unreadable field does not say.
        return

    if isinstance(thinking, dict):
        payload["thinking"] = _reshape_thinking(
            context, cast(dict[str, Any], thinking), display
        )

    _attach_effort(context, efforts_by_model)


def _reshape_thinking(
    context: RequestContext, thinking: dict[str, Any], display: ThinkingDisplayPolicy
) -> dict[str, Any]:
    reshaped = dict(thinking)
    kind = reshaped.get("type")

    descriptor = context.model_descriptor
    # `None` means routing carried no descriptor. Unreachable through `decide_route`, which raises `UnknownModel` before a `Route` exists when the provider does not describe the model — so this is a defensive read for a hand-built context, not a production state. Read as "not adaptive" all the same, because the branch that leaves the request as the client wrote it is the one that cannot break a request that works. Spec A-1.
    adaptive = descriptor.adaptive_thinking if descriptor is not None else False

    if kind == "enabled" and adaptive:
        reshaped["type"] = "adaptive"
        budget = reshaped.pop("budget_tokens", None)
        detail = f"{context.resolved_model} takes adaptive thinking only"
        if budget is not None:
            detail = f"{detail}; dropped budget_tokens={budget}"
        _record_loss(context, detail)
        logger.info(
            "rewrote thinking.type enabled -> adaptive for %r: %s",
            context.resolved_model,
            detail,
        )

    _apply_display(reshaped, display, kind=reshaped.get("type"))
    return reshaped


def _attach_effort(context: RequestContext, efforts_by_model: Mapping[str, str]) -> None:
    """Put the operator's per-model effort on the request, where one applies.

    Absent `thinking` reaches here and gets an effort, which is deliberate: on the adaptive models omitting the field runs adaptive rather than turning thinking off, so there is something for an effort to control. Only an explicit `disabled` opts out.
    """
    payload = context.payload
    thinking = payload.get("thinking")
    if isinstance(thinking, dict) and cast(dict[str, Any], thinking).get("type") == "disabled":
        # No effort on a request that asked for no thinking. The documentation says effort also bounds overall token spend, so there may be a reason to send one anyway; nothing has measured a case, and a cost dial turned by nobody's request is not something to add on a maybe. Spec A-3.
        return
    if "output_config" in payload:
        # The client used this endpoint's own vocabulary to say its own thing. Overwriting it would be a capability gate deciding what a request meant, which is not what one is for.
        return
    configured = efforts_by_model.get(context.resolved_model)
    if not configured:
        # No entry means send nothing, which upstream reads as its own default. Deliberately not a fallback value: one here would put every request on a dial nobody set.
        return
    effort = _aligned_effort(context, configured)
    if effort is not None:
        payload["output_config"] = {"effort": effort}
