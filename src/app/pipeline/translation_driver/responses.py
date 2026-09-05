"""The intermediate form for responses, and the translators either side of it.

Request translation without this is only half a crossing.
An Anthropic client asking for a Responses-backed model would receive a Responses-shaped body.

`.dev/docs/anthropic-responses-bridge/spec.md` fixes two mappings this must honour.
An `incomplete` response whose reason is the output-token limit carries `stop_reason: max_tokens`.
A legal success with no content may produce an empty text block.

Blocks are the same `ContentBlock` the request side uses, read and written by the same functions.
`D-ARCH = B` asks for one typed truth, and two block models would have been two. This file used to hold Anthropic-shaped dicts under a `kind`, which is why the Responses writer sent `arguments` as an object where the wire wants a JSON string, and why a reasoning block crossing to Anthropic arrived with an empty signature.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from app.pipeline.translation_driver.anthropic_messages import (
    block_from_anthropic,
    block_to_anthropic,
)
from app.pipeline.translation_driver.content import BlockKind, ContentBlock
from app.pipeline.translation_driver.openai_responses import (
    item_from_block,
    record_web_search_call_id_loss,
    response_blocks_from_item,
)
from app.pipeline.translation_driver.semantic import Conversion, LossCode
from app.protocols.responses_anthropic import (
    ResponseConversionError,
    anthropic_usage_from_responses,
)

TEXT = "text"

MAX_TOKENS = "max_tokens"
END_TURN = "end_turn"
TOOL_USE_STOP = "tool_use"
CONTENT_FILTER = "content_filter"

# Stop reasons that mean the turn finished, said in the Responses vocabulary of completed / incomplete / failed. `tool_use` belongs here: a turn that ends by calling a tool is one the model chose to end, not one that was cut short. The empty string is here because `SemanticResponse.stop_reason` is a bare `str`, and an unset one means nobody said — reading that as a truncation would report an observation that was never made.
#
# **This is the one copy.** The streaming framer for the same client leg (`app/pipeline/delivery/formats/openai_responses.py`) imports it from here rather than keeping its own. These two are the buffered and the streaming half of one leg, and `fef7d96` is the record of what it costs when the two halves describe one fact differently: which answer a reader sees then depends on something the reply itself does not carry. It lived here as a duplicate until 2026-08-27, kept in step by a comment; the import is what makes "the same set" checkable instead of remembered. The direction works because `delivery` already imports from `translation_driver` and never the reverse.
FINISHED_STOP_REASONS = frozenset({END_TURN, TOOL_USE_STOP, ""})

# This proxy's word for a truncation → the Responses enumeration's word for it. A forward table rather than a passthrough: `incomplete_details.reason` is an enumeration — `max_output_tokens` or `content_filter`, or null (openai SDK 3.3.1, `openai.types.responses.response.IncompleteDetails`) — so a reason not in here has no legal spelling and must become null, which is upstream's own shape for "incomplete, no reason given".
#
# Everything else that can arrive is Anthropic's own (`stop_sequence`, `pause_turn`, `refusal`, `model_context_window_exceeded`) or this proxy's synthesis (`incomplete`, written when upstream said the response was incomplete and gave no reason). A Responses client can read none of those, so they travel as `status: "incomplete"` with a null reason: the fact that the turn was cut short is the part it can act on, and a word from the wrong vocabulary would be worse than no word at all.
#
# `refusal` is deliberately not mapped onto `content_filter`. The two are neighbours, not synonyms — `config/schema.py` says so where it keeps `content_filter` off `hand_over_stop_reasons` — and this project does not invent a mapping for a shape upstream has never sent. Shared with the streaming framer the same way `FINISHED_STOP_REASONS` is, and for the same reason.
#
# `content_filter` maps to itself, and that is a different kind of entry from the one above. The reader keeps upstream's own word when it has no Anthropic spelling (`from_openai_responses_response` returns `reason or "incomplete"`), so a filtered turn arrives here already carrying the Responses enumeration's own term. Without the identity row the forward table dropped it to null on the way out, and a client that had been told *why* its turn was cut short got back only *that* it was — a round trip losing a word it never had to translate. Added 2026-08-27; this is upstream's term going home, not a mapping invented for it.
INCOMPLETE_REASONS = {MAX_TOKENS: "max_output_tokens", CONTENT_FILTER: CONTENT_FILTER}


@dataclass(slots=True)
class SemanticResponse:
    id: str = ""
    model: str = ""
    blocks: list[ContentBlock] = field(default_factory=lambda: list[ContentBlock]())
    stop_reason: str = END_TURN
    usage: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    conversion: Conversion = field(default_factory=Conversion)


def _mapping_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    entries = cast(Sequence[object], value)
    return [
        dict[str, Any](cast(Mapping[str, Any], e)) for e in entries if isinstance(e, Mapping)
    ]


def from_anthropic_response(
    payload: Mapping[str, Any],
    *,
    client_search_tool: str = "",
    hosted_web_search_expected: bool = False,
    hand_over_stop_reasons: frozenset[str] = frozenset({"max_tokens"}),
) -> SemanticResponse:
    """Accept and ignore response facts that only the Responses wire can use."""
    del client_search_tool, hosted_web_search_expected, hand_over_stop_reasons
    response = SemanticResponse(
        id=str(payload.get("id", "")),
        model=str(payload.get("model", "")),
        stop_reason=str(payload.get("stop_reason") or END_TURN),
    )
    usage = payload.get("usage")
    if isinstance(usage, Mapping):
        response.usage = dict[str, Any](cast(Mapping[str, Any], usage))

    response.blocks = [
        block_from_anthropic(block) for block in _mapping_list(payload.get("content"))
    ]
    return response


def _anthropic_usage(usage: Mapping[str, Any]) -> dict[str, Any]:
    """Responses token counts in Anthropic's keys, for a body that is about to claim to be Anthropic's.

    This used to copy the object across untouched, which handed the client `input_tokens_details` and `total_tokens` it has no schema for, no `cache_read_input_tokens` at all, and — the part that misleads rather than merely omits — an `input_tokens` that in Responses *includes* what came from cache but in Anthropic means what was sent fresh. A heavily cached prompt therefore arrived downstream looking like a full-price one. The streaming path converts, so the same route was answering with two different usage contracts depending on one flag.

    A malformed usage leaves the field empty rather than failing the response. The reply itself is complete and legal; refusing to deliver it over a count would trade the answer for its accounting, and passing the raw object through instead would put back the shape the client cannot read.
    """
    try:
        return dict[str, Any](anthropic_usage_from_responses(usage))
    except ResponseConversionError:
        return {}


def to_anthropic_response(response: SemanticResponse) -> dict[str, Any]:
    """Render a reply that arrived whole as an Anthropic message body.

    A legal success with nothing to say gets `content: []`, not a text block carrying no text. The spec permits either — it says such a reply *may* carry the empty block — so the choice is settled by what happens next: the client stores this turn and replays it, and upstream refuses an assistant turn holding a blank text block (400, `messages: text content blocks must be non-empty`) while accepting one whose content is empty (200, both mid-conversation and last). Measured 2026-08-20, `exp/260820-empty-text-probe/` F3 against F6 and F4.

    It is also the shape the streaming path already produces: it opens no content block when there is nothing to open, so a reply with no content reaches the client as a message with none. Two delivery paths for one product answered this differently until now.
    """
    content = [
        rendered
        for rendered in (
            block_to_anthropic(block, response.conversion) for block in response.blocks
        )
        if rendered is not None
    ]
    return {
        "id": response.id,
        "type": "message",
        "role": "assistant",
        "model": response.model,
        "content": content,
        "stop_reason": response.stop_reason,
        "stop_sequence": None,
        "usage": response.usage or {"input_tokens": 0, "output_tokens": 0},
    }


def _responses_stop_reason(
    payload: Mapping[str, Any],
    has_tool_call: bool,
) -> tuple[str, str | None]:
    """Map the Responses terminal state onto an Anthropic stop reason."""
    status = str(payload.get("status", "completed"))
    if status == "incomplete":
        details = payload.get("incomplete_details")
        reason = ""
        if isinstance(details, Mapping):
            reason = str(cast(Mapping[str, Any], details).get("reason", ""))
        if reason == "max_output_tokens":
            return MAX_TOKENS, None
        # Upstream's own word, unmapped, exactly as the streaming path does it. The output-token limit is the only reason with an Anthropic spelling, so it is the only one translated; everything else used to become `end_turn`, which reported a turn upstream had cut short as one it finished. The two paths described the same fact differently until this line, which is worse than either answer on its own.
        #
        # `"incomplete"` when upstream said the response was incomplete without saying why — still its own word, since that is the `status` it sent — and it keeps that case out of `end_turn` too.
        #
        # No longer recorded as a conversion loss: nothing is lost now that the reason reaches the client.
        return reason or "incomplete", None
    if has_tool_call:
        return TOOL_USE_STOP, None
    return END_TURN, None


def from_openai_responses_response(
    payload: Mapping[str, Any],
    *,
    hand_over_stop_reasons: frozenset[str] = frozenset({"max_tokens"}),
    client_search_tool: str = "",
    hosted_web_search_expected: bool = False,
) -> SemanticResponse:
    """`client_search_tool` names the tool a `tool_search_call` should be handed back as.

    It cannot be read off this payload: on the Responses wire the search *is* the tool, so the item names nothing. The request half identified it, and without that name a `tool_search_call` has nowhere to go — the client would be told the model said nothing while the model was in fact waiting for a search.
    """
    response = SemanticResponse(
        id=str(payload.get("id", "")),
        model=str(payload.get("model", "")),
    )
    usage = payload.get("usage")
    if isinstance(usage, Mapping):
        response.usage = _anthropic_usage(cast(Mapping[str, Any], usage))

    # Whether this ending will hand the turn back, which is what decides whether the block upstream cut short may be dropped at all. One setting for both, since dropping content is only defensible when the client is handed a way to get it back — separating them let a `content_filter` ending drop a block and hand over nothing, and the client lost a passage it could not ask for again on a line that read `[ OK ]`.
    #
    # Read here rather than after the loop because the drop happens inside it. The streaming assembler cannot do this: its items close before the terminal event says why, so it holds the one it cut short instead and answers the same question a moment later.
    will_hand_over, _ = _responses_stop_reason(payload, has_tool_call=False)
    for item in _mapping_list(payload.get("output")):
        record_web_search_call_id_loss(item, response.conversion)
        expected_web_search = (
            hosted_web_search_expected and item.get("type") == "web_search_call"
        )
        if (
            str(item.get("status", "")) == "incomplete"
            and not expected_web_search
            and response.blocks
            and will_hand_over in hand_over_stop_reasons
        ):
            # The item upstream cut short, dropped because something whole came before it. Same rule as the streaming assembler applies, and it has to live here rather than on the finished body: `status` is upstream's, and nothing carries it across the translation.
            #
            # The same blind spot comes with it: a `reasoning` item carries no `status` at all, so a truncated one is invisible here too. Left open deliberately; `.dev/docs/upstream/retry-and-continuation/deferred.md` §2.
            #
            # Only when something whole came before. Half a sentence still beats an empty answer, so the rule reverses when this is all there is — which is why the test is on `response.blocks` rather than on the item's position. Ruled 2026-08-21 for the streaming path and extended here 2026-08-22, when the ruling that a non-streaming turn could not be continued was withdrawn: dropping it is only defensible because the client is handed a way to get it back.
            response.conversion.record(
                LossCode.ITEM_NOT_CARRIED, f"truncated {item.get('type')!r} dropped"
            )
            continue
        _, blocks = response_blocks_from_item(
            item,
            conversion=response.conversion,
            client_search_tool=client_search_tool,
            hosted_web_search_expected=hosted_web_search_expected,
        )
        for block in blocks:
            if block.kind is BlockKind.UNKNOWN:
                response.conversion.record(
                    LossCode.ITEM_NOT_CARRIED, f"output item {item.get('type')!r}"
                )
                continue
            response.blocks.append(block)

    has_tool_call = any(block.kind is BlockKind.TOOL_USE for block in response.blocks)
    stop_reason, problem = _responses_stop_reason(payload, has_tool_call)
    response.stop_reason = stop_reason
    if problem is not None:
        response.conversion.record(LossCode.ITEM_NOT_CARRIED, problem)
    return response


def to_openai_responses_response(response: SemanticResponse) -> dict[str, Any]:
    """Render the blocks as Responses `output` items.

    Every block in a response is the assistant's, which is what makes text `output_text`.

    The terminal state is `FINISHED_STOP_REASONS` and `INCOMPLETE_REASONS`, the two tables the streaming framer for this leg imports from here. This used to be a single comparison against `max_tokens`, which said `completed` for every other way a turn can be cut short — a `refusal` reached the client as a turn the model finished, which is the shape `fef7d96` removed from the other direction. `incomplete_details` was not emitted at all, so even the one ending that did say `incomplete` never said why.
    """
    rendered = [
        item
        for item in (
            item_from_block(block, "assistant", response.conversion)
            for block in response.blocks
        )
        if item is not None
    ]
    finished = response.stop_reason in FINISHED_STOP_REASONS
    reason = None if finished else INCOMPLETE_REASONS.get(response.stop_reason)
    return {
        "id": response.id,
        "object": "response",
        "model": response.model,
        "status": "completed" if finished else "incomplete",
        # Always present, null when there is nothing legal to put in it — that is the key's shape on the wire, and it is how a client tells "no reason given" from a field this proxy forgot to write.
        "incomplete_details": {"reason": reason} if reason is not None else None,
        "output": [_as_output_item(item) for item in rendered],
        "usage": response.usage,
    }


def _as_output_item(item: dict[str, Any]) -> dict[str, Any]:
    """Wrap a bare content part in the message item a Responses `output` expects.

    The shared writer produces content parts, because in a request they sit inside a message. In a response each one is its own item, so the wrapping happens here rather than by giving the writer a second mode.
    """
    if str(item.get("type", "")) in {"output_text", "input_text", "input_image"}:
        return {"type": "message", "role": "assistant", "content": [item]}
    return item
