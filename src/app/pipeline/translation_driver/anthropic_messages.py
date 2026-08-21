"""Anthropic Messages translators.

Reads and writes the typed content model rather than moving `dict`s around. `D-ARCH = B`: wire
shapes live at this boundary and nowhere inside.
"""

from collections.abc import Mapping
from typing import Any, cast

from app.pipeline.translation_driver.content import (
    BlockKind,
    ContentBlock,
    OpaqueFormat,
    ReasoningState,
    SemanticMessage,
)
from app.pipeline.translation_driver.reasoning import (
    ReasoningIntentInvalid,
    intent_from_thinking,
)
from app.pipeline.translation_driver.reasoning_carrier import (
    decode_reasoning_carrier,
    encode_reasoning_carrier,
)
from app.pipeline.translation_driver.semantic import (
    Conversion,
    LossCode,
    SemanticRequest,
    SystemBlock,
    TranslationRefused,
    TranslationTarget,
    system_blocks_from_value,
)

WIRE_FORMAT = "anthropic-messages"

_PASSTHROUGH_KEYS = frozenset(
    {"model", "system", "messages", "tools", "stream", "max_tokens", "temperature", "thinking"}
)

TEXT = "text"
THINKING = "thinking"
REDACTED_THINKING = "redacted_thinking"
TOOL_USE = "tool_use"
TOOL_RESULT = "tool_result"
IMAGE = "image"


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries = cast(list[object], value)
    return [dict[str, Any](cast(Mapping[str, Any], e)) for e in entries if isinstance(e, Mapping)]


def _reasoning_from_signature(signature: str) -> ReasoningState:
    """Classify a `thinking.signature` by who issued it.

    A carrier this proxy (or the service it is compatible with) issued decodes back to the
    Responses payload it was holding, so it can cross. Anything else is Anthropic's own and stays
    Anthropic's own — `portable_to` is what stops it being forged into an `encrypted_content`.
    """
    decoded = decode_reasoning_carrier(signature)
    if decoded.classification == "foreign":
        return ReasoningState(OpaqueFormat.CLAUDE_SIGNATURE, signature)
    return ReasoningState(
        OpaqueFormat.PROXY_CARRIER,
        signature,
        encrypted_content=decoded.encrypted_content or "",
    )


def _block_from_anthropic(raw: dict[str, Any]) -> ContentBlock:
    kind = str(raw.get("type", ""))
    if kind == TEXT:
        return ContentBlock(BlockKind.TEXT, text=str(raw.get("text", "")), raw=raw)
    if kind == THINKING:
        signature = str(raw.get("signature", ""))
        return ContentBlock(
            BlockKind.REASONING,
            text=str(raw.get(THINKING, "")),
            reasoning=_reasoning_from_signature(signature) if signature else None,
            raw=raw,
        )
    if kind == REDACTED_THINKING:
        return ContentBlock(
            BlockKind.REASONING,
            redacted=True,
            reasoning=ReasoningState(OpaqueFormat.CLAUDE_SIGNATURE, str(raw.get("data", ""))),
            raw=raw,
        )
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
    try:
        request.reasoning = intent_from_thinking(payload.get("thinking"))
    except ReasoningIntentInvalid as invalid:
        raise TranslationRefused(
            str(invalid), code="reasoning-intent-invalid", field_path=invalid.field_path
        ) from invalid

    # Anything not claimed above is carried rather than dropped.
    # An unmodelled field therefore survives the round trip back to the same format.
    request.extensions = {
        key: value for key, value in payload.items() if key not in _PASSTHROUGH_KEYS
    }
    return request


def _system_value(blocks: list[SystemBlock]) -> list[dict[str, Any]]:
    return [{"type": TEXT, "text": block.text, **dict(block.metadata)} for block in blocks]


def block_to_anthropic(block: ContentBlock, conversion: Conversion) -> dict[str, Any] | None:
    """Render one block as Anthropic content, or None when it has no faithful rendering."""
    return _block_to_anthropic(block, conversion)


def block_from_anthropic(raw: dict[str, Any]) -> ContentBlock:
    """Read one Anthropic content block into the typed model."""
    return _block_from_anthropic(raw)


def _block_to_anthropic(block: ContentBlock, conversion: Conversion) -> dict[str, Any] | None:
    if block.kind is BlockKind.TEXT:
        return {"type": TEXT, "text": block.text}
    if block.kind is BlockKind.REASONING:
        return _reasoning_to_anthropic(block, conversion)
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
    # Image and unknown blocks have no modelled fields; their original is the only faithful
    # rendering, and returning it is what keeps a same-format crossing exact.
    if block.raw:
        return dict(block.raw)
    conversion.record(LossCode.BLOCK_NOT_CARRIED, f"{block.kind.value} into {WIRE_FORMAT}")
    return None


def _reasoning_to_anthropic(block: ContentBlock, conversion: Conversion) -> dict[str, Any]:
    """Render a reasoning block as Anthropic thinking, issuing a carrier when the state is ours.

    A Responses `encrypted_content` has no Anthropic spelling, so it travels inside a carrier this
    proxy signs. That is the reverse of the refusal on the way out: encoding *our own* value is
    honest, encoding Anthropic's would not be.
    """
    if block.redacted and block.reasoning is not None:
        return {"type": REDACTED_THINKING, "data": block.reasoning.value}
    signature = ""
    state = block.reasoning
    if state is not None:
        if state.format in {OpaqueFormat.CLAUDE_SIGNATURE, OpaqueFormat.PROXY_CARRIER}:
            # Already an Anthropic-shaped signature — ours or theirs, it goes back as it came.
            signature = state.value
        else:
            # A Responses payload has no Anthropic spelling, so it travels inside a carrier we
            # sign. Encoding our own value is recovery; encoding Anthropic's would be invention.
            signature = encode_reasoning_carrier(state.value)
    return {"type": THINKING, THINKING: block.text, "signature": signature}


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
                _block_to_anthropic(b, request.conversion) for b in message.blocks
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
    payload.update(request.extensions_for(WIRE_FORMAT))
    return payload
