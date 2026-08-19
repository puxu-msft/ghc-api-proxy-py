"""The intermediate form for responses, and the translators either side of it.

Request translation without this is only half a crossing.
An Anthropic client asking for a Responses-backed model would receive a Responses-shaped body.

`spec.md` fixes two mappings this must honour.
An `incomplete` response whose reason is the output-token limit carries `stop_reason: max_tokens`.
A legal success with no content may produce an empty text block.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from app.pipeline.translation_driver.semantic import Conversion, LossCode

TEXT = "text"
THINKING = "thinking"
TOOL_USE = "tool_use"

MAX_TOKENS = "max_tokens"
END_TURN = "end_turn"
TOOL_USE_STOP = "tool_use"


@dataclass(frozen=True, slots=True)
class SemanticBlock:
    kind: str
    payload: dict[str, Any]


@dataclass(slots=True)
class SemanticResponse:
    id: str = ""
    model: str = ""
    blocks: list[SemanticBlock] = field(default_factory=lambda: list[SemanticBlock]())
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

    for block in _mapping_list(payload.get("content")):
        kind = str(block.get("type", ""))
        response.blocks.append(SemanticBlock(kind=kind, payload=block))
    return response


def to_anthropic_response(response: SemanticResponse) -> dict[str, Any]:
    content = [block.payload for block in response.blocks]
    if not content:
        # A legal success with no content may carry one empty text block; spec.md permits it.
        content = [{"type": TEXT, "text": ""}]
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
        response.usage = dict[str, Any](cast(Mapping[str, Any], usage))

    has_tool_call = False
    for item in _mapping_list(payload.get("output")):
        item_type = str(item.get("type", ""))
        if item_type == "message":
            for part in _mapping_list(item.get("content")):
                if str(part.get("type", "")) in {"output_text", "text"}:
                    response.blocks.append(
                        SemanticBlock(TEXT, {"type": TEXT, "text": str(part.get("text", ""))})
                    )
                else:
                    response.conversion.record(
                        LossCode.BLOCK_NOT_CARRIED,
                        f"content part {part.get('type')!r}",
                    )
        elif item_type == "function_call":
            has_tool_call = True
            response.blocks.append(
                SemanticBlock(
                    TOOL_USE,
                    {
                        "type": TOOL_USE,
                        "id": str(item.get("call_id") or item.get("id", "")),
                        "name": str(item.get("name", "")),
                        "input": item.get("arguments", {}),
                    },
                )
            )
        elif item_type == "reasoning":
            response.blocks.append(
                SemanticBlock(
                    THINKING,
                    {"type": THINKING, "thinking": _reasoning_text(item), "signature": ""},
                )
            )
        else:
            response.conversion.record(LossCode.ITEM_NOT_CARRIED, f"output item {item_type!r}")

    stop_reason, problem = _responses_stop_reason(payload, has_tool_call)
    response.stop_reason = stop_reason
    if problem is not None:
        response.conversion.record(LossCode.ITEM_NOT_CARRIED, problem)
    return response


def _reasoning_text(item: Mapping[str, Any]) -> str:
    """Join a reasoning item's summary parts.

    Parts inside one item concatenate; items never merge with each other.
    """
    return "".join(str(part.get("text", "")) for part in _mapping_list(item.get("summary")))


def to_openai_responses_response(response: SemanticResponse) -> dict[str, Any]:
    output: list[dict[str, Any]] = []
    for block in response.blocks:
        if block.kind == TEXT:
            output.append(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": str(block.payload.get("text", ""))}
                    ],
                }
            )
        elif block.kind == TOOL_USE:
            output.append(
                {
                    "type": "function_call",
                    "call_id": str(block.payload.get("id", "")),
                    "name": str(block.payload.get("name", "")),
                    "arguments": block.payload.get("input", {}),
                }
            )
        elif block.kind == THINKING:
            output.append(
                {
                    "type": "reasoning",
                    "summary": [
                        {"type": "summary_text", "text": str(block.payload.get(THINKING, ""))}
                    ],
                }
            )
        else:
            response.conversion.record(LossCode.BLOCK_NOT_CARRIED, f"block {block.kind!r}")

    return {
        "id": response.id,
        "object": "response",
        "model": response.model,
        "status": "incomplete" if response.stop_reason == MAX_TOKENS else "completed",
        "output": output,
        "usage": response.usage,
    }
