"""Shared OpenAI Responses item normalization.

This module is the semantic seam between Responses request/response codecs and
stream delivery. It knows how one Responses item maps to the typed content
model, but it does not know about HTTP, SSE, downstream delivery, or commit
frontiers.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from app.pipeline import anthropic_server_tools
from app.pipeline.server_tool_text import web_search_call_text
from app.pipeline.translation_driver.content import BlockKind, ContentBlock
from app.pipeline.translation_driver.reasoning_bridge import (
    ReasoningBridgeError,
    read_responses_reasoning,
)
from app.pipeline.translation_driver.semantic import Conversion, LossCode, TranslationRefused

TEXT = "text"
TOOL_SEARCH_CALL = "tool_search_call"
TOOL_SEARCH_OUTPUT = "tool_search_output"
WEB_SEARCH_CALL = "web_search_call"


@dataclass(frozen=True, slots=True)
class ResponsesItemContext:
    """Request-scoped facts needed to interpret a Responses item."""

    client_search_tool: str = ""
    hosted_web_search_expected: bool = False
    allow_incomplete_tool_arguments: bool = False


_DEFAULT_CONTEXT = ResponsesItemContext()


def normalize_input_item(
    item: Mapping[str, Any],
    *,
    context: ResponsesItemContext = _DEFAULT_CONTEXT,
) -> tuple[str, tuple[ContentBlock, ...]]:
    """Read a Responses input item into typed content blocks."""
    return _normalize_item(item, context=context)


def normalize_response_item(
    item: Mapping[str, Any],
    *,
    context: ResponsesItemContext = _DEFAULT_CONTEXT,
    conversion: Conversion,
) -> tuple[str, tuple[ContentBlock, ...]]:
    """Read one Responses output item and record response-side losses."""
    if item.get("type") == WEB_SEARCH_CALL:
        record_web_search_call_id_loss(dict(item), conversion)
        if not context.hosted_web_search_expected:
            conversion.record(
                LossCode.SERVER_TOOL_NOT_CARRIED,
                anthropic_server_tools.unsolicited_web_search_loss(item.get("action")),
            )
            return _normalize_item(item, context=context)

        pair = anthropic_server_tools.unavailable_web_search_pair(item.get("action"))
        conversion.record(
            LossCode.SERVER_TOOL_PARTIALLY_REPRESENTABLE,
            anthropic_server_tools.partial_web_search_loss(pair, item.get("status")),
        )
        return "assistant", (
            ContentBlock(
                BlockKind.SERVER_TOOL_USE,
                call_id=str(pair.call["id"]),
                name=anthropic_server_tools.WEB_SEARCH,
                arguments=pair.action.input,
                raw=pair.call,
            ),
            ContentBlock(
                BlockKind.WEB_SEARCH_TOOL_RESULT,
                call_id=str(pair.call["id"]),
                output=pair.result["content"],
                raw=pair.result,
            ),
        )

    return _normalize_item(item, context=context)


def record_web_search_call_id_loss(
    item: Mapping[str, Any],
    conversion: Conversion,
) -> None:
    if item.get("type") != WEB_SEARCH_CALL:
        return
    detail = anthropic_server_tools.web_search_call_id_loss(item.get("id"))
    if detail is not None:
        conversion.record(LossCode.SERVER_TOOL_CALL_ID_NOT_CARRIED, detail)


def _normalize_item(
    item: Mapping[str, Any],
    *,
    context: ResponsesItemContext,
) -> tuple[str, tuple[ContentBlock, ...]]:
    kind = str(item.get("type", ""))
    if kind == TOOL_SEARCH_OUTPUT:
        return "assistant", ()
    if kind == TOOL_SEARCH_CALL and context.client_search_tool:
        arguments = item.get("arguments")
        return "assistant", (
            ContentBlock(
                BlockKind.TOOL_USE,
                call_id=str(item.get("call_id") or item.get("id", "")),
                name=context.client_search_tool,
                arguments=arguments if isinstance(arguments, dict) else {},
                raw=item,
            ),
        )
    if kind == "message":
        return (
            str(item.get("role", "user")),
            tuple(
                _block_from_content_part(part)
                for part in _mapping_list(item.get("content"))
            ),
        )
    if kind == "function_call":
        return "assistant", (
            ContentBlock(
                BlockKind.TOOL_USE,
                call_id=str(item.get("call_id") or item.get("id", "")),
                name=str(item.get("name", "")),
                arguments=_decoded_arguments(
                    item.get("arguments"),
                    allow_malformed=context.allow_incomplete_tool_arguments,
                ),
                raw=item,
            ),
        )
    if kind == "function_call_output":
        return "user", (
            ContentBlock(
                BlockKind.TOOL_RESULT,
                call_id=str(item.get("call_id", "")),
                output=item.get("output"),
                raw=item,
            ),
        )
    if kind == "reasoning":
        try:
            reasoning = read_responses_reasoning(item)
        except ReasoningBridgeError as error:
            raise TranslationRefused(
                error.detail,
                code=error.code,
                field_path="input.reasoning",
            ) from error
        return "assistant", (
            ContentBlock(BlockKind.REASONING, reasoning=reasoning, raw=item),
        )
    if kind == WEB_SEARCH_CALL:
        return "assistant", (
            ContentBlock(
                BlockKind.TEXT,
                text=web_search_call_text(item.get("action")),
                raw=item,
            ),
        )
    return "user", (ContentBlock(BlockKind.UNKNOWN, raw=item),)


def _mapping_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries = cast(list[object], value)
    return [
        dict[str, Any](cast(Mapping[str, Any], entry))
        for entry in entries
        if isinstance(entry, Mapping)
    ]


def _block_from_content_part(part: dict[str, Any]) -> ContentBlock:
    kind = str(part.get("type", ""))
    if kind in {"input_text", "output_text", "text"}:
        return ContentBlock(BlockKind.TEXT, text=str(part.get("text", "")), raw=part)
    if kind == "input_image":
        return ContentBlock(BlockKind.IMAGE, raw=part)
    return ContentBlock(BlockKind.UNKNOWN, raw=part)


def _decoded_arguments(value: object, *, allow_malformed: bool = False) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        if allow_malformed:
            return {"__raw": value}
        raise TranslationRefused(
            "function_call arguments must be valid JSON",
            code="invalid-tool-arguments",
            field_path="output.function_call.arguments",
        ) from error


__all__ = [
    "ResponsesItemContext",
    "normalize_input_item",
    "normalize_response_item",
    "record_web_search_call_id_loss",
]
