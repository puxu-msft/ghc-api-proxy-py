"""Anthropic Messages translators.

Reads and writes the typed content model rather than moving `dict`s around. `D-ARCH = B`: wire shapes live at this boundary and nowhere inside.
"""

from collections.abc import Mapping
from typing import Any, cast

from app.pipeline.translation_driver.content import BlockKind, ContentBlock, SemanticMessage
from app.pipeline.translation_driver.reasoning import (
    ReasoningIntentInvalid,
    intent_from_thinking,
    unused_thinking_fields,
)
from app.pipeline.translation_driver.reasoning_bridge import (
    ReasoningBridgeError,
    ReasoningNotPortable,
    read_anthropic_reasoning,
    reasoning_to_anthropic,
)
from app.pipeline.translation_driver.semantic import (
    Conversion,
    LossCode,
    SemanticRequest,
    SystemBlock,
    ToolChoiceNotSupported,
    TranslationRefused,
    TranslationTarget,
    system_blocks_from_value,
)
from app.pipeline.translation_driver.tool_choice import intent_from_anthropic_tool_choice

WIRE_FORMAT = "anthropic-messages"

_PASSTHROUGH_KEYS = frozenset(
    {"model", "system", "messages", "tools", "stream", "max_tokens", "temperature", "thinking", "tool_choice"}
)

TEXT = "text"
THINKING = "thinking"
REDACTED_THINKING = "redacted_thinking"
TOOL_USE = "tool_use"
TOOL_RESULT = "tool_result"
SERVER_TOOL_USE = "server_tool_use"
WEB_SEARCH_TOOL_RESULT = "web_search_tool_result"
IMAGE = "image"


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries = cast(list[object], value)
    return [dict[str, Any](cast(Mapping[str, Any], e)) for e in entries if isinstance(e, Mapping)]


def _dict_value(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return dict[str, Any](cast(Mapping[str, Any], value))


def _block_from_anthropic(raw: dict[str, Any]) -> ContentBlock:
    kind = str(raw.get("type", ""))
    if kind == TEXT:
        return ContentBlock(BlockKind.TEXT, text=str(raw.get("text", "")), raw=raw)
    if kind in {THINKING, REDACTED_THINKING}:
        try:
            reasoning = read_anthropic_reasoning(raw)
        except ReasoningBridgeError as error:
            raise TranslationRefused(
                error.detail,
                code=error.code,
                field_path=f"messages.content.{kind}",
            ) from error
        return ContentBlock(BlockKind.REASONING, reasoning=reasoning, raw=raw)
    if kind == TOOL_USE:
        return ContentBlock(
            BlockKind.TOOL_USE,
            call_id=str(raw.get("id", "")),
            name=str(raw.get("name", "")),
            arguments=raw.get("input"),
            raw=raw,
        )
    if kind == TOOL_RESULT:
        return ContentBlock(
            BlockKind.TOOL_RESULT,
            call_id=str(raw.get("tool_use_id", "")),
            output=raw.get("content"),
            is_error=bool(raw.get("is_error", False)),
            raw=raw,
        )
    if kind == SERVER_TOOL_USE:
        return ContentBlock(
            BlockKind.SERVER_TOOL_USE,
            call_id=str(raw.get("id", "")),
            name=str(raw.get("name", "")),
            arguments=raw.get("input"),
            raw=raw,
        )
    if kind == WEB_SEARCH_TOOL_RESULT:
        return ContentBlock(
            BlockKind.WEB_SEARCH_TOOL_RESULT,
            call_id=str(raw.get("tool_use_id", "")),
            output=raw.get("content"),
            raw=raw,
        )
    if kind == IMAGE:
        return ContentBlock(BlockKind.IMAGE, raw=raw)
    return ContentBlock(BlockKind.UNKNOWN, raw=raw)


def _message_from_anthropic(raw: Mapping[str, Any]) -> SemanticMessage:
    role = str(raw.get("role", ""))
    content = raw.get("content")
    if isinstance(content, str):
        return SemanticMessage(role, (ContentBlock(BlockKind.TEXT, text=content),))
    return SemanticMessage(role, tuple(_block_from_anthropic(b) for b in _dict_list(content)))


def from_anthropic_messages(payload: Mapping[str, Any]) -> SemanticRequest:
    blocks, problem = system_blocks_from_value(payload.get("system"))
    model = payload.get("model")
    raw_messages = payload.get("messages")
    request = SemanticRequest(
        model=model if isinstance(model, str) else "",
        system=blocks,
        messages=[
            _message_from_anthropic(cast(Mapping[str, Any], m))
            for m in (raw_messages if isinstance(raw_messages, list) else [])  # pyright: ignore[reportUnknownVariableType]
            if isinstance(m, Mapping)
        ],
        tools=_dict_list(payload.get("tools")),
        stream=bool(payload.get("stream", False)),
        source_format=WIRE_FORMAT,
    )
    if problem is not None:
        request.conversion.record(problem, "system")

    max_tokens = payload.get("max_tokens")
    if isinstance(max_tokens, int):
        request.max_output_tokens = max_tokens
    temperature = payload.get("temperature")
    if isinstance(temperature, int | float):
        request.temperature = float(temperature)
    # Read into an intent here rather than left for the writer, so an unreadable `thinking` is refused while the client's own field name is still in scope to name in the error. What the intent then becomes on the wire depends on the target model and is not this side's business.
    thinking = payload.get("thinking")
    try:
        request.reasoning = intent_from_thinking(thinking)
    except ReasoningIntentInvalid as invalid:
        raise TranslationRefused(
            str(invalid), code="reasoning-intent-invalid", field_path=invalid.field_path
        ) from invalid
    # Claiming `thinking` took it out of `extensions`, which is where an unclaimed field's loss used to be reported. Whatever the mode did not read is named here instead, so `{"type": "disabled", "budget_tokens": 8000}` does not answer "nothing was lost" about a budget it ignored.
    unread = unused_thinking_fields(thinking, request.reasoning)
    if unread:
        request.conversion.record(
            LossCode.REASONING_INTENT_APPROXIMATED,
            f"thinking fields not read by this intent: {', '.join(unread)}",
        )

    # Read the client's intent once; unclaimed shapes stay in extensions for same-format replay.
    choice = payload.get("tool_choice")
    request.tool_choice = intent_from_anthropic_tool_choice(choice)

    # Anything not claimed above is carried rather than dropped.
    # An unmodelled field therefore survives the round trip back to the same format.
    request.extensions = {
        key: value for key, value in payload.items() if key not in _PASSTHROUGH_KEYS
    }
    if request.tool_choice is None and "tool_choice" in payload:
        request.extensions["tool_choice"] = choice
    return request


def _system_value(blocks: list[SystemBlock]) -> list[dict[str, Any]]:
    return [{"type": TEXT, "text": block.text, **dict(block.metadata)} for block in blocks]


def block_to_anthropic(block: ContentBlock, conversion: Conversion) -> dict[str, Any] | None:
    """Render one response block for an Anthropic client."""
    return _block_to_anthropic(block, conversion, bridge_for_client=True)


def block_from_anthropic(raw: dict[str, Any]) -> ContentBlock:
    """Read one Anthropic content block into the typed model."""
    return _block_from_anthropic(raw)


def _block_to_anthropic(
    block: ContentBlock,
    conversion: Conversion,
    *,
    bridge_for_client: bool,
) -> dict[str, Any] | None:
    if block.kind is BlockKind.TEXT:
        return {"type": TEXT, "text": block.text}
    if block.kind is BlockKind.REASONING:
        return _reasoning_to_anthropic(
            block,
            conversion,
            bridge_for_client=bridge_for_client,
        )
    if block.kind is BlockKind.TOOL_USE:
        return {
            "type": TOOL_USE,
            "id": block.call_id,
            "name": block.name,
            "input": block.arguments if block.arguments is not None else {},
        }
    if block.kind is BlockKind.TOOL_RESULT:
        result: dict[str, Any] = {"type": TOOL_RESULT, "tool_use_id": block.call_id}
        if block.output is not None:
            result["content"] = block.output
        if block.is_error:
            result["is_error"] = True
        return result
    if block.kind is BlockKind.SERVER_TOOL_USE:
        if block.raw.get("type") == SERVER_TOOL_USE:
            return dict(block.raw)
        return {
            "type": SERVER_TOOL_USE,
            "id": block.call_id,
            "name": block.name,
            "input": _dict_value(block.arguments),
        }
    if block.kind is BlockKind.WEB_SEARCH_TOOL_RESULT:
        if block.raw.get("type") == WEB_SEARCH_TOOL_RESULT:
            return dict(block.raw)
        if block.output is None:
            conversion.record(
                LossCode.BLOCK_NOT_CARRIED,
                "web_search_tool_result has no content",
            )
            return None
        return {
            "type": WEB_SEARCH_TOOL_RESULT,
            "tool_use_id": block.call_id,
            "content": block.output,
        }
    # Image and unknown blocks have no modelled fields; their original is the only faithful rendering, and returning it is what keeps a same-format crossing exact.
    if block.raw:
        return dict(block.raw)
    conversion.record(LossCode.BLOCK_NOT_CARRIED, f"{block.kind.value} into {WIRE_FORMAT}")
    return None


def _reasoning_to_anthropic(
    block: ContentBlock,
    conversion: Conversion,
    *,
    bridge_for_client: bool,
) -> dict[str, Any] | None:
    """Render reasoning natively, or put provider-specific state in a client carrier."""
    content = block.reasoning
    if content is None:
        conversion.record(LossCode.BLOCK_NOT_CARRIED, "reasoning block has no typed content")
        return None
    try:
        return reasoning_to_anthropic(content, bridge_for_client=bridge_for_client)
    except ReasoningNotPortable:
        state = content.state
        source = state.format.value if state is not None else content.source_format
        conversion.record(
            LossCode.REASONING_STATE_NOT_PORTABLE,
            f"{source} cannot be written to an Anthropic upstream",
        )
        return None


def to_anthropic_messages(
    request: SemanticRequest, target_model: TranslationTarget | None = None
) -> dict[str, Any]:
    # `target_model` is accepted and unused. Every outbound translator takes it so the registry can hand one to all of them alike; what a model can do only changes the rendering on the leg that has to choose an upstream-specific spelling, and Anthropic's own format has no such choice to make here.
    del target_model
    messages: list[dict[str, Any]] = []
    for message in request.messages:
        rendered = [
            block
            for block in (
                _block_to_anthropic(
                    b,
                    request.conversion,
                    bridge_for_client=False,
                )
                for b in message.blocks
            )
            if block is not None
        ]
        messages.append({"role": message.role, "content": rendered})

    payload: dict[str, Any] = {"model": request.model, "messages": messages}
    if request.system:
        payload["system"] = _system_value(request.system)
    if request.tools:
        payload["tools"] = request.tools
    if request.stream:
        payload["stream"] = True
    if request.max_output_tokens is not None:
        payload["max_tokens"] = request.max_output_tokens
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    _restore_thinking(payload, request)
    _restore_tool_choice(payload, request)
    payload.update(request.extensions_for(WIRE_FORMAT))
    return payload


def _restore_thinking(payload: dict[str, Any], request: SemanticRequest) -> None:
    """Put `thinking` back on the way out to this same format.

    The reader claims `thinking` now, which takes it out of `extensions` — and `extensions` is what used to carry an unclaimed field across a same-format round trip untouched. Claiming a field without rebuilding it is therefore how a round trip starts losing it, and the loss is silent because the field simply is not there on the other side.

    `effort` has no Anthropic spelling: it is what a Responses request says, and there is no budget that means the same thing. Reported rather than invented.
    """
    intent = request.reasoning
    if intent is None:
        return
    if intent.mode == "disabled":
        payload["thinking"] = {"type": "disabled"}
    elif intent.mode == "adaptive":
        payload["thinking"] = {"type": "adaptive"}
    elif intent.mode == "budget" and intent.budget_tokens is not None:
        payload["thinking"] = {"type": "enabled", "budget_tokens": intent.budget_tokens}
    else:
        request.conversion.record(
            LossCode.REASONING_INTENT_NOT_CARRIED,
            f"{intent.mode} reasoning has no Anthropic spelling",
        )


def _restore_tool_choice(payload: dict[str, Any], request: SemanticRequest) -> None:
    """Render the intent without relaxing a selection the target cannot honor."""
    crossing = request.source_format != WIRE_FORMAT
    intent = request.tool_choice
    if intent is None:
        if crossing and "tool_choice" in request.extensions:
            raise ToolChoiceNotSupported("tool_choice has no supported Anthropic translation")
        return
    if intent.mode in {"auto", "any", "none"}:
        choice: dict[str, Any] = {"type": intent.mode}
    elif intent.mode == "tool" and intent.name:
        choice = {"type": "tool", "name": intent.name}
    else:
        raise ToolChoiceNotSupported(f"{intent.mode} tool choice has no Anthropic spelling")
    if crossing:
        if not payload.get("tools"):
            if intent.mode in {"any", "tool"}:
                raise ToolChoiceNotSupported("a forced tool choice requires declared tools")
            return
        if intent.mode == "tool" and not any(
            tool.get("name") == intent.name for tool in request.tools
        ):
            raise ToolChoiceNotSupported(f"{intent.name} is not declared by the tools this request sends")
    if intent.disable_parallel is not None:
        choice["disable_parallel_tool_use"] = intent.disable_parallel
    payload["tool_choice"] = choice
