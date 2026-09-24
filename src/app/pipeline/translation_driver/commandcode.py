"""Command Code's native request codec over the semantic IR.

Command Code is not an OpenAI-compatible endpoint. Its upstream body is a
runtime envelope containing a Chat-like ``params`` object, and its response is
an NDJSON event stream. This module owns only the IR-to-wire request projection;
transport and event assembly stay in the provider and delivery layers.
"""

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast

import orjson

from app.pipeline.translation_driver.content import (
    BlockKind,
    ContentBlock,
    ReasoningContent,
)
from app.pipeline.translation_driver.options import TranslationOptions
from app.pipeline.translation_driver.reasoning import EffortSource
from app.pipeline.translation_driver.responses import SemanticResponse
from app.pipeline.translation_driver.semantic import (
    LossCode,
    SemanticMessage,
    SemanticRequest,
    ToolChoiceNotSupported,
    TranslationRefused,
    TranslationTarget,
)
from app.pipeline.translation_driver.usage import responses_usage_from_anthropic

WIRE_FORMAT = "commandcode"
COMMANDCODE_MAX_TOKENS = 200_000
COMMANDCODE_DEFAULT_MAX_TOKENS = 64_000
_STOP_REASONS = {
    "stop": "end_turn",
    "tool-calls": "tool_use",
    "tool_calls": "tool_use",
    "length": "max_tokens",
}
_EMPTY_FUNCTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
}
_RAW_TOOL_INPUT_KEY = "__raw"
_CONSUMED_EXTENSIONS = frozenset({"prompt_cache_key"})
_CONSUMED_NESTED_EXTENSIONS = {
    "thinking": frozenset({"type", "budget_tokens"}),
}
_RESPONSES_REFUSED_FIELDS = (
    "background",
    "context_management",
    "conversation",
    "include",
    "max_tool_calls",
    "moderation",
    "prompt",
    "stream_options",
    "text",
    "top_logprobs",
    "top_p",
    "truncation",
)


def _commandcode_effort(request: SemanticRequest) -> str | None:
    """Choose Command Code effort without turning Anthropic's default into high."""
    intent = request.thinking_effort
    if intent is None:
        return None
    if intent.effort_source in {EffortSource.RESPONSES, EffortSource.CHAT_COMPLETIONS}:
        return intent.effort
    if intent.effort_source is EffortSource.ANTHROPIC_TOP_LEVEL:
        return intent.effort
    if intent.effort_source is EffortSource.ANTHROPIC_PER_MESSAGE:
        return intent.effort

    thinking = request.nested_extensions.get("thinking")
    if thinking is None:
        return "none" if not intent.enabled else None
    if not intent.enabled:
        return "none"
    if thinking.get("type") == "adaptive" or (
        intent.effort_source is EffortSource.ANTHROPIC_DEFAULT
        and "budget_tokens" not in thinking
    ):
        return "medium"
    budget = thinking.get("budget_tokens")
    if type(budget) is int and budget > 0:
        if budget <= 2000:
            return "low"
        if budget <= 5000:
            return "medium"
        return "high"
    return None


def _text_from_output(
    value: object,
    request: SemanticRequest,
    *,
    call_id: str,
) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = cast(list[object], value)
        text: list[str] = []
        dropped = False
        for part in parts:
            if isinstance(part, str):
                text.append(part)
                continue
            if not isinstance(part, Mapping):
                dropped = True
                continue
            entry = cast(Mapping[str, Any], part)
            if entry.get("type") in {"text", "input_text", "output_text"}:
                content = entry.get("text")
                if isinstance(content, str):
                    text.append(content)
                elif content is not None:
                    text.append(str(content))
                else:
                    dropped = True
                continue
            dropped = True
        if dropped:
            request.conversion.record(
                LossCode.TOOL_RESULT_CONTENT_FLATTENED,
                f"non-text Command Code tool result content for {call_id!r}",
            )
        return "".join(text)
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def _image_from_block(block: ContentBlock) -> dict[str, Any] | None:
    raw = block.raw
    image_url = raw.get("image_url")
    if isinstance(image_url, str) and image_url:
        return {"type": "image", "image": image_url}
    if isinstance(image_url, Mapping):
        url = cast(Mapping[str, Any], image_url).get("url")
        if isinstance(url, str) and url:
            return {"type": "image", "image": url}
    url = raw.get("image")
    if isinstance(url, str) and url:
        return {"type": "image", "image": url}
    source = raw.get("source")
    if isinstance(source, dict):
        source_map = cast(dict[str, Any], source)
        source_type = source_map.get("type")
        if source_type == "url" and isinstance(source_map.get("url"), str):
            return {"type": "image", "image": source_map["url"]}
        if (
            source_type == "base64"
            and isinstance(source_map.get("data"), str)
            and isinstance(source_map.get("media_type"), str)
        ):
            return {
                "type": "image",
                "image": f"data:{source_map['media_type']};base64,{source_map['data']}",
            }
    return None


def _record_responses_image_losses(
    block: ContentBlock,
    request: SemanticRequest,
) -> None:
    if request.source_format != "openai-responses":
        return
    if block.raw.get("type") != "input_image":
        return
    for field_name in ("detail", "prompt_cache_breakpoint"):
        if field_name in block.raw:
            request.conversion.record(
                LossCode.EXTENSIONS_NOT_CARRIED,
                "Responses input_image field "
                f"'input[].content[].{field_name}' has no Command Code representation",
            )


def _tool_result(
    block: ContentBlock,
    request: SemanticRequest,
    tool_names: Mapping[str, str],
) -> dict[str, Any]:
    output = _text_from_output(block.output, request, call_id=block.call_id)
    if block.is_error:
        request.conversion.record(
            LossCode.TOOL_RESULT_ERROR_MARKED,
            f"tool result for {block.call_id!r} uses Command Code's text error marker",
        )
        output = f"[tool_error] {output}"
    return {
        "type": "tool-result",
        "toolCallId": block.call_id,
        "toolName": block.name or tool_names.get(block.call_id, ""),
        "output": {"type": "text", "value": output},
    }


def _message_content(
    message: SemanticMessage,
    request: SemanticRequest,
    tool_names: Mapping[str, str],
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    for block in message.blocks:
        if block.kind is BlockKind.TEXT:
            part: dict[str, Any] = {"type": "text", "text": block.text}
            if isinstance(block.raw.get("cache_control"), Mapping):
                part["cache_control"] = dict(
                    cast(Mapping[str, Any], block.raw["cache_control"])
                )
            content.append(part)
        elif block.kind is BlockKind.REASONING:
            reasoning = block.reasoning
            if reasoning is None:
                continue
            if reasoning.state is not None:
                request.conversion.record_nonportable_reasoning()
                if not reasoning.visible_text:
                    field_path = (
                        "input.reasoning.encrypted_content"
                        if reasoning.source_format == "openai-responses"
                        else "messages[].content[].signature"
                    )
                    raise TranslationRefused(
                        "Command Code cannot carry encrypted-only reasoning history",
                        code="commandcode-reasoning-state-not-supported",
                        field_path=field_path,
                    )
            if reasoning.visible_text:
                content.append({"type": "reasoning", "text": reasoning.visible_text})
        elif block.kind is BlockKind.IMAGE:
            _record_responses_image_losses(block, request)
            image = _image_from_block(block)
            if image is None:
                detail = "image block has no Command Code image data"
                if isinstance(block.raw.get("file_id"), str):
                    detail = "Responses image file_id has no Command Code representation"
                request.conversion.record(
                    LossCode.BLOCK_NOT_CARRIED,
                    detail,
                )
            else:
                content.append(image)
        elif block.kind is BlockKind.TOOL_USE:
            content.append(
                {
                    "type": "tool-call",
                    "toolCallId": block.call_id,
                    "toolName": block.name,
                    "input": block.arguments if block.arguments is not None else {},
                }
            )
        elif block.kind is BlockKind.TOOL_RESULT:
            content.append(_tool_result(block, request, tool_names))
        elif block.kind is BlockKind.UNKNOWN:
            request.conversion.record(
                LossCode.BLOCK_NOT_CARRIED,
                f"unknown block in {message.role!r} message has no Command Code mapping",
            )
        else:
            request.conversion.record(
                LossCode.BLOCK_NOT_CARRIED,
                f"{block.kind.value} block has no Command Code mapping",
            )
    return content


def _commandcode_messages(
    request: SemanticRequest,
    tool_names: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Render messages while giving each tool result its native role."""
    messages: list[dict[str, Any]] = []
    for message in request.messages:
        phase = message.phase
        if phase is None:
            phase = message.raw.get("phase")
        if phase is not None:
            request.conversion.record(
                LossCode.MESSAGE_PHASE_NOT_CARRIED,
                f"Responses message phase {phase!r} has no Command Code representation",
            )
        if message.role != "user":
            blocks = message.blocks
            if message.role == "assistant":
                blocks = tuple(
                    [
                        block
                        for block in blocks
                        if block.kind is BlockKind.REASONING
                    ]
                    + [
                        block
                        for block in blocks
                        if block.kind is not BlockKind.REASONING
                    ]
                )
                message = SemanticMessage(
                    message.role,
                    blocks,
                    message.raw,
                    message.phase,
                )
            content = _message_content(message, request, tool_names)
            if content:
                messages.append({"role": message.role, "content": content})
            continue

        pending: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        for block in message.blocks:
            if block.kind is BlockKind.TOOL_RESULT:
                tool_results.append(
                    {
                        "role": "tool",
                        "content": [_tool_result(block, request, tool_names)],
                    }
                )
                continue
            pending.extend(
                _message_content(
                    SemanticMessage(message.role, (block,)),
                    request,
                    tool_names,
                )
            )
        messages.extend(tool_results)
        if pending:
            messages.append({"role": "user", "content": pending})
    return messages


def _tool_choice(request: SemanticRequest) -> dict[str, Any] | None:
    intent = request.tool_choice
    if intent is None:
        return None
    if intent.mode in {"auto", "none"}:
        return {"type": intent.mode}
    if intent.mode == "any":
        return {"type": "any"}
    if intent.mode == "tool" and intent.name:
        return {"type": "tool", "name": intent.name}
    raise ToolChoiceNotSupported(f"{intent.mode} tool choice has no Command Code spelling")


def _refuse_unclaimed_responses_tool_choice(request: SemanticRequest) -> None:
    if request.source_format != "openai-responses":
        return
    choice = request.extensions.get("tool_choice")
    if choice is None:
        return
    raise TranslationRefused(
        "Command Code cannot preserve this Responses tool choice",
        code="commandcode-tool-choice-not-supported",
        field_path="tool_choice",
    )


def _commandcode_tools(request: SemanticRequest) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    supported_fields = frozenset(
        {"type", "name", "description", "input_schema", "parameters"}
    )
    for index, tool in enumerate(request.tools):
        declared_type = tool.get("type")
        if (
            declared_type not in (None, "function")
            or (
                request.source_format == "openai-responses"
                and declared_type != "function"
            )
        ):
            request.conversion.record(
                LossCode.ITEM_NOT_CARRIED,
                f"Command Code cannot represent tool[{index}] type {declared_type!r}",
            )
            continue
        name = tool.get("name")
        if not isinstance(name, str) or not name:
            request.conversion.record(
                LossCode.ITEM_NOT_CARRIED,
                f"Command Code function tool[{index}] has no non-empty name",
            )
            continue
        for field_name in sorted(set(tool) - supported_fields):
            request.conversion.record(
                LossCode.EXTENSIONS_NOT_CARRIED,
                f"Command Code function tool[{index}] field {field_name!r} has no representation",
            )
        converted.append(
            {
                "type": "function",
                "name": name,
                "description": _tool_description(tool, request, index),
                "input_schema": _tool_schema(tool, request, index),
            }
        )
    return converted


def _validate_commandcode_tool_choice(
    request: SemanticRequest,
    tools: list[dict[str, Any]],
) -> None:
    intent = request.tool_choice
    if intent is None:
        return
    if intent.mode == "tool":
        available = {
            name
            for tool in tools
            if isinstance((name := tool.get("name")), str) and name
        }
        if intent.name not in available:
            raise TranslationRefused(
                "Command Code cannot preserve a forced choice for a tool it sends",
                code="commandcode-tool-choice-not-supported",
                field_path="tool_choice",
            )
    elif intent.mode == "any" and not tools:
        raise TranslationRefused(
            "Command Code cannot preserve a required tool choice without function tools",
            code="commandcode-tool-choice-not-supported",
            field_path="tool_choice",
        )


def _tool_description(
    tool: Mapping[str, Any],
    request: SemanticRequest,
    index: int,
) -> str:
    value = tool.get("description")
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    request.conversion.record(
        LossCode.TOOL_DESCRIPTION_COERCED,
        f"Command Code function tool[{index}] description was coerced to a string",
    )
    return str(value)


def _tool_schema(
    tool: Mapping[str, Any],
    request: SemanticRequest,
    index: int,
) -> dict[str, Any]:
    value = tool.get("input_schema")
    if value is None:
        value = tool.get("parameters")
    if value is None:
        return dict(_EMPTY_FUNCTION_SCHEMA)
    if isinstance(value, Mapping):
        return dict[str, Any](cast(Mapping[str, Any], value))
    request.conversion.record(
        LossCode.EXTENSIONS_NOT_CARRIED,
        f"Command Code function tool[{index}] schema was not an object; sent an empty object schema",
    )
    return dict(_EMPTY_FUNCTION_SCHEMA)


def _decode_tool_input(value: object, response: SemanticResponse | None = None) -> Any:
    if isinstance(value, Mapping):
        return dict[str, Any](cast(Mapping[str, Any], value))
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            if response is not None:
                response.conversion.record(
                    LossCode.UPSTREAM_ERROR_NOT_INTERPRETED,
                    "Command Code tool input was not valid JSON",
                )
            return {_RAW_TOOL_INPUT_KEY: value}
    return value if value is not None else {}


def _has_raw_tool_input(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    mapping = cast(Mapping[str, Any], value)
    return (
        set(mapping) == {_RAW_TOOL_INPUT_KEY}
        and isinstance(mapping.get(_RAW_TOOL_INPUT_KEY), str)
    )


def _tool_call_id(value: object, fallback_index: int) -> str:
    return str(value) if value else f"call_{fallback_index}"


@dataclass(slots=True)
class CommandCodeEventAccumulator:
    """Incrementally convert Command Code events into semantic content blocks."""

    model: str = ""
    blocks: list[ContentBlock] = field(
        default_factory=lambda: list[ContentBlock]()
    )
    stop_reason: str = ""
    usage: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    usage_seen: bool = False
    output_tokens_seen: bool = False
    output_tokens: int | None = None
    _cut_mid_block: bool = False
    _current_kind: str = ""
    _current_text: str = ""
    _tool_id: str = ""
    _tool_name: str = ""
    _tool_input: str | None = None

    def push(self, event: Mapping[str, Any]) -> tuple[ContentBlock, ...]:
        kind = str(event.get("type", ""))
        model = event.get("model")
        if isinstance(model, str) and model:
            self.model = model
        if kind == "text-start":
            completed = self._flush_current()
            self.blocks.extend(completed)
            return completed
        if kind in {"start", "start-step"}:
            return ()
        if kind == "text-delta":
            return self._append_text(str(event.get("text") or event.get("delta") or ""))
        if kind == "reasoning-start":
            completed = self._flush_current()
            self.blocks.extend(completed)
            self._current_kind = BlockKind.REASONING.value
            self._current_text = ""
            return completed
        if kind == "reasoning-delta":
            if self._current_kind != BlockKind.REASONING.value:
                completed = self._flush_current()
                self.blocks.extend(completed)
                self._current_kind = BlockKind.REASONING.value
                self._current_text = str(event.get("text", ""))
                return completed
            self._current_text += str(event.get("text", ""))
            return ()
        if kind == "tool-call":
            fallback_index = len(self.blocks)
            completed = list(self._flush_current())
            block = ContentBlock(
                BlockKind.TOOL_USE,
                call_id=_tool_call_id(event.get("toolCallId"), fallback_index),
                name=str(event.get("toolName", "")),
                arguments=_decode_tool_input(event.get("input")),
            )
            completed.append(block)
            self.blocks.extend(completed)
            return tuple(completed)
        if kind == "tool-input-start":
            fallback_index = len(self.blocks)
            completed = self._flush_current()
            self.blocks.extend(completed)
            self._current_kind = BlockKind.TOOL_USE.value
            self._tool_id = _tool_call_id(event.get("toolCallId"), fallback_index)
            self._tool_name = str(event.get("toolName", ""))
            self._tool_input = None
            return completed
        if kind == "tool-input-delta":
            if self._current_kind != BlockKind.TOOL_USE.value:
                completed = self._flush_current()
                self.blocks.extend(completed)
                self._current_kind = BlockKind.TOOL_USE.value
            else:
                completed = ()
            delta = str(event.get("input") or event.get("delta") or "")
            self._tool_input = (self._tool_input or "") + delta
            return completed
        if kind == "text-end":
            if self._current_kind != BlockKind.TEXT.value:
                return ()
            completed = self._flush_current()
            self.blocks.extend(completed)
            return completed
        if kind == "reasoning-end":
            if self._current_kind != BlockKind.REASONING.value:
                return ()
            completed = self._flush_current()
            self.blocks.extend(completed)
            return completed
        if kind == "tool-input-end":
            if self._current_kind != BlockKind.TOOL_USE.value:
                return ()
            completed = self._flush_current()
            self.blocks.extend(completed)
            return completed
        if kind == "finish-step":
            self._update_usage(event.get("usage"))
            if isinstance(event.get("finishReason"), str):
                self.stop_reason = _STOP_REASONS.get(
                    str(event["finishReason"]), str(event["finishReason"])
                )
            return ()
        if kind == "finish":
            completed = self._flush_current()
            self.blocks.extend(completed)
            self._update_usage(event.get("totalUsage") or event.get("usage"))
            finish_reason = event.get("finishReason")
            if isinstance(finish_reason, str) and finish_reason:
                self.stop_reason = _STOP_REASONS.get(finish_reason, finish_reason)
            elif not self.stop_reason:
                self.stop_reason = "tool_use" if any(
                    block.kind is BlockKind.TOOL_USE for block in self.blocks
                ) else "end_turn"
            return completed
        return ()

    def finish(self) -> tuple[ContentBlock, ...]:
        self._discard_current(mark_cut=True)
        return ()

    @property
    def has_open_block(self) -> bool:
        return bool(self._current_kind)

    @property
    def cut_mid_block(self) -> bool:
        return self._cut_mid_block or self.has_open_block

    def _append_text(self, text: str) -> tuple[ContentBlock, ...]:
        if not text:
            return ()
        if self._current_kind != BlockKind.TEXT.value:
            completed = self._flush_current()
            self.blocks.extend(completed)
            self._current_kind = BlockKind.TEXT.value
            self._current_text = text
            return completed
        self._current_text += text
        return ()

    def _discard_current(self, *, mark_cut: bool = False) -> None:
        if self._current_kind and mark_cut:
            self._cut_mid_block = True
        self._current_kind = ""
        self._current_text = ""
        self._tool_id = ""
        self._tool_name = ""
        self._tool_input = None

    def _flush_current(self) -> tuple[ContentBlock, ...]:
        if not self._current_kind:
            return ()
        if self._current_kind == BlockKind.TEXT.value:
            block = ContentBlock(BlockKind.TEXT, text=self._current_text)
        elif self._current_kind == BlockKind.REASONING.value:
            block = ContentBlock(
                BlockKind.REASONING,
                reasoning=ReasoningContent(
                    visible_text=self._current_text,
                    source_format=WIRE_FORMAT,
                ),
            )
        elif self._current_kind == BlockKind.TOOL_USE.value:
            block = ContentBlock(
                BlockKind.TOOL_USE,
                call_id=self._tool_id,
                name=self._tool_name,
                arguments=_decode_tool_input(self._tool_input),
            )
        else:
            self._current_kind = ""
            self._current_text = ""
            return ()
        self._current_kind = ""
        self._current_text = ""
        self._tool_id = ""
        self._tool_name = ""
        self._tool_input = None
        return (block,)

    def _update_usage(self, value: object) -> None:
        if isinstance(value, Mapping):
            mapped = dict[str, Any](cast(Mapping[str, Any], value))
            self.usage_seen = True
            self.usage.update(mapped)
            for key in ("outputTokens", "output_tokens"):
                if key not in mapped:
                    continue
                candidate = mapped[key]
                if type(candidate) is int and candidate >= 0:
                    self.output_tokens_seen = True
                    self.output_tokens = candidate
                break


def commandcode_usage_to_anthropic(usage: Mapping[str, Any]) -> dict[str, Any]:
    def integer(*keys: str) -> int:
        for key in keys:
            value = usage.get(key)
            if type(value) is int and value >= 0:
                return value
        return 0

    input_tokens = integer("inputTokens", "input_tokens")
    output_tokens = integer("outputTokens", "output_tokens")
    details = usage.get("inputTokenDetails")
    if details is None:
        details = usage.get("input_tokens_details")
    detail_map: Mapping[str, Any] = (
        cast(Mapping[str, Any], details) if isinstance(details, Mapping) else {}
    )
    cache_read_detail = _optional_integer(
        detail_map,
        "cacheReadTokens",
        "cache_read_tokens",
    )
    cached_top_level = _optional_integer(
        usage,
        "cachedInputTokens",
        "cached_input_tokens",
    )
    cached = (
        cache_read_detail
        if cache_read_detail is not None
        else cached_top_level
        if cached_top_level is not None
        else 0
    )
    cache_write = _optional_integer(
        detail_map,
        "cacheWriteTokens",
        "cache_write_tokens",
    )
    no_cache = _optional_integer(detail_map, "noCacheTokens", "no_cache_tokens")
    cache_write_tokens = cache_write if cache_write is not None else 0
    input_tokens_fresh = (
        no_cache
        if no_cache is not None
        else max(0, input_tokens - cached - cache_write_tokens)
    )
    converted: dict[str, Any] = {
        "input_tokens": input_tokens_fresh,
        "output_tokens": output_tokens,
    }
    if cached:
        converted["cache_read_input_tokens"] = cached
    if cache_write_tokens:
        converted["cache_creation_input_tokens"] = cache_write_tokens
    output_details = usage.get("outputTokenDetails")
    if output_details is None:
        output_details = usage.get("output_tokens_details")
    output_detail_map: Mapping[str, Any] = (
        cast(Mapping[str, Any], output_details)
        if isinstance(output_details, Mapping)
        else {}
    )
    reasoning_tokens = output_detail_map.get(
        "reasoningTokens",
        output_detail_map.get("reasoning_tokens"),
    )
    if type(reasoning_tokens) is int and reasoning_tokens >= 0:
        converted["reasoning_tokens"] = reasoning_tokens
    return converted


def _optional_integer(
    value: Mapping[str, Any],
    *keys: str,
) -> int | None:
    for key in keys:
        candidate = value.get(key)
        if type(candidate) is int and candidate >= 0:
            return candidate
    return None


def commandcode_usage_to_responses(
    usage: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Render Command Code usage in the complete Responses usage shape."""
    if not usage:
        return None
    return responses_usage_from_anthropic(commandcode_usage_to_anthropic(usage))


def from_commandcode_response(
    payload: Mapping[str, Any],
    *,
    options: TranslationOptions | None = None,
    client_search_tool: str = "",
    hosted_web_search_expected: bool = False,
    hand_over_stop_reasons: frozenset[str] = frozenset({"max_tokens"}),
) -> SemanticResponse:
    del options, client_search_tool, hosted_web_search_expected, hand_over_stop_reasons
    events = payload.get("events")
    accumulator = CommandCodeEventAccumulator(model=str(payload.get("model", "")))
    if isinstance(events, Sequence) and not isinstance(events, str | bytes):
        for event in cast(Sequence[object], events):
            if isinstance(event, Mapping):
                accumulator.push(cast(Mapping[str, Any], event))
    accumulator.finish()
    raw_id = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    response = SemanticResponse(
        id=f"cc_{sha256(raw_id).hexdigest()[:24]}",
        model=accumulator.model or str(payload.get("model", "")),
        blocks=list(accumulator.blocks),
        stop_reason=accumulator.stop_reason or "incomplete",
        usage=(
            commandcode_usage_to_anthropic(accumulator.usage)
            if accumulator.usage_seen
            else {}
        ),
        source_format=WIRE_FORMAT,
    )
    for block in response.blocks:
        if block.kind is BlockKind.TOOL_USE and _has_raw_tool_input(block.arguments):
            response.conversion.record(
                LossCode.UPSTREAM_ERROR_NOT_INTERPRETED,
                f"Command Code tool input for {block.call_id!r} was not valid JSON",
            )
    return response


def to_commandcode(
    request: SemanticRequest,
    target_model: TranslationTarget | None = None,
    *,
    options: TranslationOptions | None = None,
) -> dict[str, Any]:
    """Render a Command Code generation envelope from the semantic IR."""
    target = target_model or (options.target if options is not None else None)
    for field_name in ("previous_response_id", "store"):
        if field_name in request.extensions:
            raise TranslationRefused(
                f"Command Code does not support Responses state field {field_name!r}",
                code="commandcode-state-not-supported",
                field_path=field_name,
            )
    if request.source_format == "openai-responses":
        for field_name in _RESPONSES_REFUSED_FIELDS:
            if field_name in request.extensions:
                raise TranslationRefused(
                    "Command Code cannot preserve Responses control "
                    f"{field_name!r}",
                    code="commandcode-responses-control-not-supported",
                    field_path=field_name,
                )
    _refuse_unclaimed_responses_tool_choice(request)
    if request.max_output_tokens is not None and (
        isinstance(request.max_output_tokens, bool)
        or request.max_output_tokens <= 0
    ):
        field_path = (
            "max_output_tokens"
            if request.source_format == "openai-responses"
            else "max_tokens"
        )
        raise TranslationRefused(
            "Command Code max output tokens must be a positive integer",
            code="commandcode-max-output-tokens-invalid",
            field_path=field_path,
        )

    system = "\n\n".join(block.text for block in request.system if block.text)
    for block in request.system:
        if block.metadata:
            request.conversion.record(
                LossCode.SYSTEM_METADATA_NOT_CARRIED,
                "Command Code system is a single string",
            )

    messages: list[dict[str, Any]] = []
    tool_names = {
        block.call_id: block.name
        for message in request.messages
        for block in message.blocks
        if block.kind is BlockKind.TOOL_USE and block.call_id and block.name
    }
    messages.extend(_commandcode_messages(request, tool_names))
    if request.extensions.get("prompt_cache_key"):
        for message in messages:
            if message["role"] != "user":
                continue
            parts = message["content"]
            if not isinstance(parts, list):
                continue
            for part in reversed(cast(list[object], parts)):
                if not isinstance(part, dict):
                    continue
                part_map = cast(dict[str, Any], part)
                if part_map.get("type") != "text":
                    continue
                part_map.setdefault("cache_control", {"type": "ephemeral"})
                break
            else:
                continue
            break
    if not system and not messages:
        field_path = "input" if request.source_format == "openai-responses" else "messages"
        raise TranslationRefused(
            "Command Code requires system content or at least one message",
            code="commandcode-messages-empty",
            field_path=field_path,
        )

    params: dict[str, Any] = {
        "model": target.model_id if target is not None and target.model_id else request.model,
        "messages": messages,
        "max_tokens": min(
            request.max_output_tokens
            if request.max_output_tokens is not None
            else COMMANDCODE_DEFAULT_MAX_TOKENS,
            COMMANDCODE_MAX_TOKENS,
        ),
        # Command Code's generation endpoint always streams; the provider
        # aggregates events when the client requested a buffered response.
        "stream": True,
    }
    if not request.stream:
        request.conversion.record(
            LossCode.COMMANDCODE_STREAM_FORCED,
            "Command Code generation always uses an upstream event stream",
        )
    if system:
        params["system"] = system
    if request.temperature is not None:
        params["temperature"] = request.temperature
    effort = _commandcode_effort(request)
    if effort is not None:
        params["reasoning_effort"] = effort
    elif (
        request.thinking_effort is not None
        and request.thinking_effort.enabled
        and (
            request.thinking_effort.effort_source is not EffortSource.ANTHROPIC_DEFAULT
            or "thinking" in request.nested_extensions
        )
    ):
        request.conversion.record(
            LossCode.REASONING_INTENT_NOT_CARRIED,
            "Command Code received reasoning enablement without an effort level",
        )
    tools = _commandcode_tools(request) if request.tools else []
    _validate_commandcode_tool_choice(request, tools)
    if tools:
        params["tools"] = tools
    choice = _tool_choice(request)
    if choice is not None:
        params["tool_choice"] = choice
    parallel_tool_calls = request.parallel_tool_calls
    if (
        parallel_tool_calls is None
        and request.tool_choice is not None
        and request.tool_choice.disable_parallel is not None
    ):
        parallel_tool_calls = not request.tool_choice.disable_parallel
    if parallel_tool_calls is not None:
        params["parallel_tool_calls"] = parallel_tool_calls
    params.update(
        request.nested_extensions_for(
            WIRE_FORMAT,
            excluded=_CONSUMED_NESTED_EXTENSIONS,
        )
    )
    params.update(
        request.extensions_for(
            WIRE_FORMAT,
            excluded=_CONSUMED_EXTENSIONS,
        )
    )

    return {
        "config": {
            "workingDir": os.getcwd(),
            "date": datetime.now(UTC).date().isoformat(),
            "environment": "production",
            "structure": [],
            "isGitRepo": False,
            "currentBranch": "",
            "mainBranch": "",
            "gitStatus": "",
        },
        "memory": None,
        "taste": None,
        "skills": "",
        "permissionMode": "standard",
        "params": params,
    }
