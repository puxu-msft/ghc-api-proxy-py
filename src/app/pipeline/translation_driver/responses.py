"""The intermediate form for responses, and the translators either side of it.

Request translation without this is only half a crossing.
An Anthropic client asking for a Responses-backed model would receive a Responses-shaped body.

`spec.md` fixes two mappings this must honour.
An `incomplete` response whose reason is the output-token limit carries `stop_reason: max_tokens`.
A legal success with no content may produce an empty text block.

Blocks are the same `ContentBlock` the request side uses, read and written by the same functions.
`D-ARCH = B` asks for one typed truth, and two block models would have been two. This file used to
hold Anthropic-shaped dicts under a `kind`, which is why the Responses writer sent `arguments` as
an object where the wire wants a JSON string, and why a reasoning block crossing to Anthropic
arrived with an empty signature.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from app.pipeline.translation_driver.anthropic_messages import (
    block_from_anthropic,
    block_to_anthropic,
)
from app.pipeline.translation_driver.content import BlockKind, ContentBlock
from app.pipeline.translation_driver.openai_responses import blocks_from_item, item_from_block
from app.pipeline.translation_driver.semantic import Conversion, LossCode
from app.protocols.responses_anthropic import (
    ResponseConversionError,
    anthropic_usage_from_responses,
)

TEXT = "text"

MAX_TOKENS = "max_tokens"
END_TURN = "end_turn"
TOOL_USE_STOP = "tool_use"


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


def from_anthropic_response(payload: Mapping[str, Any]) -> SemanticResponse:
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
        return END_TURN, f"incomplete response with reason {reason!r}"
    if has_tool_call:
        return TOOL_USE_STOP, None
    return END_TURN, None


def from_openai_responses_response(payload: Mapping[str, Any]) -> SemanticResponse:
    response = SemanticResponse(
        id=str(payload.get("id", "")),
        model=str(payload.get("model", "")),
    )
    usage = payload.get("usage")
    if isinstance(usage, Mapping):
        response.usage = _anthropic_usage(cast(Mapping[str, Any], usage))

    for item in _mapping_list(payload.get("output")):
        _, blocks = blocks_from_item(item)
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
    """
    rendered = [
        item
        for item in (
            item_from_block(block, "assistant", response.conversion)
            for block in response.blocks
        )
        if item is not None
    ]
    return {
        "id": response.id,
        "object": "response",
        "model": response.model,
        "status": "incomplete" if response.stop_reason == MAX_TOKENS else "completed",
        "output": [_as_output_item(item) for item in rendered],
        "usage": response.usage,
    }


def _as_output_item(item: dict[str, Any]) -> dict[str, Any]:
    """Wrap a bare content part in the message item a Responses `output` expects.

    The shared writer produces content parts, because in a request they sit inside a message. In a
    response each one is its own item, so the wrapping happens here rather than by giving the
    writer a second mode.
    """
    if str(item.get("type", "")) in {"output_text", "input_text", "input_image"}:
        return {"type": "message", "role": "assistant", "content": [item]}
    return item
