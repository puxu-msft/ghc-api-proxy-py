"""OpenAI Responses translators.

`model-translation.md` shows `instructions` as an array of role-bearing objects, and notes we do
not need that flexibility yet. The Copilot upstream does not offer it either: measured on
2026-08-18, it accepts `instructions` only as a string and answers `failed to parse request` to
every array form tried — `[str]`, `[{role, content: str}]`, `[{role, content: [{type: text}]}]`,
the same with `input_text`, and with an explicit `type: message`. So the blocks are joined here.

That drops the per-block `cache_control` marker, which `Conversion` records — but it does not drop
prompt caching. Measured on 2026-08-18: the same 24082-token body sent twice with a plain string
`instructions` and no cache field at all reported `cached_tokens` 0 then 24079. This endpoint
caches by prefix on its own, so the marker Anthropic needs has nothing to do here. Sending the
Anthropic field anyway is refused — `Unknown parameter: 'input[0].content[0].cache_control'`.

The Anthropic passthrough path keeps the blocks and their markers intact.
"""

import json
from collections.abc import Callable, Mapping
from typing import Any, cast

from app.config.schema import SystemPromptPlacement
from app.pipeline.translation_driver.content import (
    BlockKind,
    ContentBlock,
    OpaqueFormat,
    ReasoningState,
    SemanticMessage,
)
from app.pipeline.translation_driver.semantic import (
    Conversion,
    LossCode,
    SemanticRequest,
    SystemBlock,
    system_blocks_from_value,
)

WIRE_FORMAT = "openai-responses"

_PASSTHROUGH_KEYS = frozenset(
    {"model", "instructions", "input", "tools", "stream", "max_output_tokens", "temperature"}
)
SYSTEM_ROLE = "system"


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries = cast(list[object], value)
    return [dict[str, Any](cast(Mapping[str, Any], e)) for e in entries if isinstance(e, Mapping)]


def _blocks_from_instructions(value: object) -> tuple[list[SystemBlock], LossCode | None]:
    """Read `instructions`, which may be a string or role-bearing entries."""
    if isinstance(value, str) or value is None:
        return system_blocks_from_value(value)
    if not isinstance(value, list):
        return [], LossCode.SYSTEM_FIELD_MALFORMED

    blocks: list[SystemBlock] = []
    problem: LossCode | None = None
    for entry in cast(list[object], value):
        if not isinstance(entry, Mapping):
            problem = LossCode.SYSTEM_FIELD_MALFORMED
            continue
        item = cast(Mapping[str, Any], entry)
        role = item.get("role")
        if role is not None and role != SYSTEM_ROLE:
            # Roles other than system are part of the richer shape we do not use yet.
            problem = LossCode.INSTRUCTIONS_ROLE_NOT_CARRIED
            continue
        found, issue = system_blocks_from_value(item.get("content"))
        blocks.extend(found)
        problem = problem or issue
    return blocks, problem


def from_openai_responses(payload: Mapping[str, Any]) -> SemanticRequest:
    blocks, problem = _blocks_from_instructions(payload.get("instructions"))
    model = payload.get("model")
    request = SemanticRequest(
        model=model if isinstance(model, str) else "",
        system=blocks,
        messages=_messages_from_input(payload.get("input")),
        tools=_dict_list(payload.get("tools")),
        stream=bool(payload.get("stream", False)),
        source_format=WIRE_FORMAT,
    )
    if problem is not None:
        request.conversion.record(problem, "instructions")

    max_output = payload.get("max_output_tokens")
    if isinstance(max_output, int):
        request.max_output_tokens = max_output
    temperature = payload.get("temperature")
    if isinstance(temperature, int | float):
        request.temperature = float(temperature)

    request.extensions = {
        key: value for key, value in payload.items() if key not in _PASSTHROUGH_KEYS
    }
    return request


def _instructions_value(blocks: list[SystemBlock], request: SemanticRequest) -> str:
    """Join the system blocks into the one shape this upstream accepts.

    Blank-line separated so two blocks do not run into one sentence. Per-block metadata is named
    rather than dropped in silence — `cache_control` in practice, which this endpoint neither takes
    nor needs, since it caches by prefix without being told where the boundaries are.
    """
    dropped = sorted({key for block in blocks for key in block.metadata})
    if dropped:
        request.conversion.record(
            LossCode.SYSTEM_METADATA_NOT_CARRIED,
            f"into {WIRE_FORMAT} instructions: {', '.join(dropped)}",
        )
    return "\n\n".join(block.text for block in blocks)


def _function_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Put one tool in the shape the Responses endpoint takes.

    Anthropic names the schema `input_schema` and carries no `type`; Responses wants a flat
    function tool with `parameters`. Passing the Anthropic shape through earns
    `One of the tools requested is invalid.` — measured 2026-08-18.

    A tool that already looks like a Responses tool is left alone, so a Responses-to-Responses
    round trip does not get rewritten.
    """
    if "input_schema" not in tool:
        return tool
    converted = {key: value for key, value in tool.items() if key != "input_schema"}
    converted["type"] = tool.get("type", "function")
    converted["parameters"] = tool["input_schema"]
    return converted


def _messages_from_input(value: object) -> list[SemanticMessage]:
    """Read Responses `input` items back into typed messages.

    Each item becomes its own message, because Responses has no message grouping to preserve: a
    `function_call` is a top-level item, not a block inside an assistant turn.
    """
    messages: list[SemanticMessage] = []
    for item in _dict_list(value):
        kind = str(item.get("type", ""))
        if kind == "message":
            role = str(item.get("role", "user"))
            blocks = tuple(
                _block_from_content_part(part) for part in _dict_list(item.get("content"))
            )
            messages.append(SemanticMessage(role, blocks))
        elif kind == "function_call":
            messages.append(
                SemanticMessage(
                    "assistant",
                    (
                        ContentBlock(
                            BlockKind.TOOL_USE,
                            call_id=str(item.get("call_id") or item.get("id", "")),
                            name=str(item.get("name", "")),
                            arguments=_decoded_arguments(item.get("arguments")),
                            raw=item,
                        ),
                    ),
                )
            )
        elif kind == "function_call_output":
            messages.append(
                SemanticMessage(
                    "user",
                    (
                        ContentBlock(
                            BlockKind.TOOL_RESULT,
                            call_id=str(item.get("call_id", "")),
                            output=item.get("output"),
                            raw=item,
                        ),
                    ),
                )
            )
        elif kind == "reasoning":
            encrypted = str(item.get("encrypted_content", ""))
            messages.append(
                SemanticMessage(
                    "assistant",
                    (
                        ContentBlock(
                            BlockKind.REASONING,
                            text=_summary_text(item.get("summary")),
                            reasoning=(
                                ReasoningState(OpaqueFormat.RESPONSES_ENCRYPTED, encrypted)
                                if encrypted
                                else None
                            ),
                            raw=item,
                        ),
                    ),
                )
            )
        else:
            messages.append(
                SemanticMessage("user", (ContentBlock(BlockKind.UNKNOWN, raw=item),))
            )
    return messages


def _block_from_content_part(part: dict[str, Any]) -> ContentBlock:
    kind = str(part.get("type", ""))
    if kind in {"input_text", "output_text", "text"}:
        return ContentBlock(BlockKind.TEXT, text=str(part.get("text", "")), raw=part)
    if kind == "input_image":
        return ContentBlock(BlockKind.IMAGE, raw=part)
    return ContentBlock(BlockKind.UNKNOWN, raw=part)


def _summary_text(value: object) -> str:
    return "".join(str(part.get("text", "")) for part in _dict_list(value))


def _decoded_arguments(value: object) -> Any:
    """`arguments` is a JSON string on the wire; the model holds the decoded value.

    A string that does not parse is kept as-is rather than discarded — a malformed tool call is
    still what the model produced, and losing it would hide the defect.
    """
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


# Measured against real traffic on 2026-08-18: the existing service sends exactly these item
# shapes for the same conversation — `message` with `input_text`, `function_call` whose
# `arguments` is a JSON *string*, `function_call_output` whose `output` is a string, and
# `reasoning` carrying `encrypted_content`.
def _input_from_messages(
    messages: list[SemanticMessage],
    conversion: Conversion,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in messages:
        parts: list[dict[str, Any]] = []
        for block in message.blocks:
            item = _item_from_block(block, message.role, conversion)
            if item is not None:
                # Text and images belong inside one message item; everything else is top-level,
                # so an accumulated message must be flushed before the standalone item goes out
                # or the conversation order changes.
                if "type" in item and item["type"] in {"input_text", "output_text", "input_image"}:
                    parts.append(item)
                    continue
                if parts:
                    items.append(_message_item(message.role, parts))
                    parts = []
                items.append(item)
        if parts:
            items.append(_message_item(message.role, parts))
    return items


def _message_item(role: str, parts: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "message", "role": role, "content": parts}


def _item_from_block(
    block: ContentBlock,
    role: str,
    conversion: Conversion,
) -> dict[str, Any] | None:
    if block.kind is BlockKind.TEXT:
        # `output_text` is the assistant's own words; anything the model is being *given* is
        # `input_text`, which is why the role decides rather than the block.
        part_type = "output_text" if role == "assistant" else "input_text"
        return {"type": part_type, "text": block.text}
    if block.kind is BlockKind.IMAGE:
        return dict(block.raw) if block.raw else None
    if block.kind is BlockKind.TOOL_USE:
        return {
            "type": "function_call",
            "call_id": block.call_id,
            "name": block.name,
            "arguments": _encoded_arguments(block.arguments),
        }
    if block.kind is BlockKind.TOOL_RESULT:
        return {
            "type": "function_call_output",
            "call_id": block.call_id,
            "output": _flattened_output(block, conversion),
        }
    if block.kind is BlockKind.REASONING:
        return _reasoning_item(block, conversion)
    conversion.record(LossCode.BLOCK_NOT_CARRIED, f"{block.kind.value} into {WIRE_FORMAT}")
    return None


def _encoded_arguments(value: Any) -> str:
    """Responses wants a JSON string here, not an object. Sending an object is a 400."""
    if isinstance(value, str):
        return value
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _flattened_output(block: ContentBlock, conversion: Conversion) -> str:
    """`function_call_output.output` is a string, while Anthropic's `content` may be blocks.

    Text blocks join; anything else has no slot here and is recorded rather than silently
    swallowed, which is what happens to an image inside a tool result.
    """
    output = block.output
    if isinstance(output, str):
        return output
    if output is None:
        return ""
    if isinstance(output, list):
        texts: list[str] = []
        dropped = False
        for part in cast(list[object], output):
            if isinstance(part, Mapping):
                entry = cast(Mapping[str, Any], part)
                if str(entry.get("type", "")) == "text":
                    texts.append(str(entry.get("text", "")))
                    continue
            dropped = True
        if dropped:
            conversion.record(
                LossCode.TOOL_RESULT_CONTENT_FLATTENED,
                f"non-text tool result content for {block.call_id}",
            )
        return "".join(texts)
    return json.dumps(output, ensure_ascii=False)


def _reasoning_item(block: ContentBlock, conversion: Conversion) -> dict[str, Any] | None:
    """Render reasoning, or refuse and say so.

    Refusing matters more than rendering. Anthropic's signature is a value only Anthropic can
    produce; writing it into `encrypted_content` would hand upstream something it never issued.
    A carrier this proxy signed is different — the Responses payload is inside it, and taking it
    back out is recovery, not invention.
    """
    state = block.reasoning
    if state is None:
        return {"type": "reasoning", "summary": _summary_parts(block.text)}
    if state.format is OpaqueFormat.RESPONSES_ENCRYPTED:
        return {
            "type": "reasoning",
            "summary": _summary_parts(block.text),
            "encrypted_content": state.value,
        }
    if state.format is OpaqueFormat.PROXY_CARRIER and state.encrypted_content:
        return {
            "type": "reasoning",
            "summary": _summary_parts(block.text),
            "encrypted_content": state.encrypted_content,
        }
    conversion.record(
        LossCode.REASONING_STATE_NOT_PORTABLE,
        f"{state.format.value} cannot be written as {WIRE_FORMAT} encrypted_content",
    )
    return None


def _summary_parts(text: str) -> list[dict[str, Any]]:
    return [{"type": "summary_text", "text": text}] if text else []


def _place_in_instructions(payload: dict[str, Any], request: SemanticRequest) -> None:
    """`instructions-joint-string`: the blocks as one string in the top-level field."""
    payload["instructions"] = _instructions_value(request.system, request)


# Total rather than defaulted, the same reasoning as `layout_strategy` in the request hook: the
# schema admits exactly the spellings the config defines, so a missing case is a bug here rather
# than an operator's typo, and a fallback would silently reshape the request.
#
# One entry today. A second — `as-role-system`, the prompt as a `role: system` message at the head
# of `input` — adds a function and a line; the endpoint was measured to accept that shape.
_SYSTEM_PROMPT_PLACEMENTS: dict[
    SystemPromptPlacement, Callable[[dict[str, Any], SemanticRequest], None]
] = {
    "instructions-joint-string": _place_in_instructions,
}


def to_openai_responses(
    request: SemanticRequest,
    *,
    system_prompts: SystemPromptPlacement = "instructions-joint-string",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": request.model,
        "input": _input_from_messages(request.messages, request.conversion),
    }
    if request.system:
        _SYSTEM_PROMPT_PLACEMENTS[system_prompts](payload, request)
    if request.tools:
        payload["tools"] = [_function_tool(tool) for tool in request.tools]
    if request.stream:
        payload["stream"] = True
    if request.max_output_tokens is not None:
        payload["max_output_tokens"] = request.max_output_tokens
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    payload.update(request.extensions_for(WIRE_FORMAT))
    return payload
