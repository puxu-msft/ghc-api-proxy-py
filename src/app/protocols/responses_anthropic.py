from __future__ import annotations

from base64 import urlsafe_b64encode
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Never, cast

import orjson

from app.anthropic.thinking.responses_reasoning import responses_reasoning_to_anthropic
from app.models.anthropic import AnthropicUsage, ContentBlock, MessagesResponse
from app.protocols.anthropic_responses import ToolNameMapper

type JsonObject = dict[str, Any]

_ANTHROPIC_MESSAGE_ID_NAMESPACE = b"ghc-api-proxy:anthropic-message-id:v1\0"


@dataclass(frozen=True, slots=True)
class ResponseConversionFact:
    code: str
    field_path: str


@dataclass(frozen=True, slots=True)
class ConvertedResponse:
    message: MessagesResponse
    upstream_response_id: str
    upstream_model: str
    facts: tuple[ResponseConversionFact, ...]


class ResponseConversionError(ValueError):
    def __init__(self, message: str, *, code: str, field_path: str) -> None:
        super().__init__(message)
        self.code = code
        self.field_path = field_path


def convert_responses_response_to_anthropic(
    response: Mapping[str, Any],
    *,
    tool_name_mapper: ToolNameMapper | None = None,
) -> ConvertedResponse:
    """Convert one complete Responses JSON body into an Anthropic message."""
    response_id = _required_string(response, "id", "id")
    model = _required_string(response, "model", "model")
    status = _required_string(response, "status", "status")
    if status == "failed":
        _fail("status", "failed_response", "Responses upstream returned a failed response")
    if status != "completed":
        _fail(
            "status",
            "unsupported_response_status",
            f"unsupported Responses status {status!r}",
        )

    output = response.get("output")
    if not isinstance(output, Sequence) or isinstance(output, (str, bytes, bytearray)):
        _fail("output", "invalid_response", "Responses output must be a list")
    output_items = cast(Sequence[object], output)

    mapper = tool_name_mapper or ToolNameMapper()
    content: list[ContentBlock] = []
    has_tool_use = False
    for item_index, value in enumerate(output_items):
        path = f"output[{item_index}]"
        item = _mapping(value, path)
        item_type = _required_string(item, "type", f"{path}.type")
        if item_type == "message":
            content.extend(_convert_message(item, path))
        elif item_type == "function_call":
            content.append(_convert_function_call(item, path, mapper))
            has_tool_use = True
        elif item_type == "reasoning":
            blocks = responses_reasoning_to_anthropic([item])
            if blocks is None:
                _fail(path, "invalid_reasoning", "invalid Responses reasoning item")
            content.extend(ContentBlock.model_validate(block) for block in blocks)
        elif _is_server_tool_item(item_type):
            _fail(path, "server_tool_not_supported", "server tools are not revived")
        else:
            _fail(
                f"{path}.type",
                "unsupported_output_item",
                f"unsupported Responses output item {item_type!r}",
            )

    if not content:
        content.append(ContentBlock(type="text", text=""))

    return ConvertedResponse(
        message=MessagesResponse(
            id=anthropic_message_id_from_response_id(response_id),
            model=model,
            content=content,
            stop_reason="tool_use" if has_tool_use else "end_turn",
            stop_sequence=None,
            usage=_convert_usage(response.get("usage")),
        ),
        upstream_response_id=response_id,
        upstream_model=model,
        facts=(ResponseConversionFact(code="response_id_transformed", field_path="id"),),
    )


def anthropic_message_id_from_response_id(upstream_response_id: str) -> str:
    """Map an upstream identity to a stable, opaque Anthropic message identity."""
    digest = sha256(
        _ANTHROPIC_MESSAGE_ID_NAMESPACE + upstream_response_id.encode("utf-8")
    ).digest()[:24]
    token = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"msg_{token}"


def _convert_message(item: Mapping[str, Any], path: str) -> list[ContentBlock]:
    parts = item.get("content")
    if not isinstance(parts, Sequence) or isinstance(parts, (str, bytes, bytearray)):
        _fail(f"{path}.content", "invalid_message", "message content must be a list")
    content_parts = cast(Sequence[object], parts)

    blocks: list[ContentBlock] = []
    for part_index, value in enumerate(content_parts):
        part_path = f"{path}.content[{part_index}]"
        part = _mapping(value, part_path)
        part_type = _required_string(part, "type", f"{part_path}.type")
        if part_type != "output_text":
            _fail(
                f"{part_path}.type",
                "unsupported_content_part",
                f"unsupported Responses content part {part_type!r}",
            )
        text = part.get("text")
        if not isinstance(text, str):
            _fail(f"{part_path}.text", "invalid_message", "output_text requires text")
        blocks.append(ContentBlock(type="text", text=text))
    return blocks


def _convert_function_call(
    item: Mapping[str, Any],
    path: str,
    mapper: ToolNameMapper,
) -> ContentBlock:
    call_id = _required_string(item, "call_id", f"{path}.call_id")
    name = _required_string(item, "name", f"{path}.name")
    arguments = _required_string(item, "arguments", f"{path}.arguments", allow_empty=True)
    try:
        parsed = orjson.loads(arguments)
    except orjson.JSONDecodeError as error:
        raise ResponseConversionError(
            "function_call arguments must be valid JSON",
            code="invalid_tool_arguments",
            field_path=f"{path}.arguments",
        ) from error
    if not isinstance(parsed, dict):
        _fail(
            f"{path}.arguments",
            "invalid_tool_arguments",
            "function_call arguments must decode to an object",
        )
    return ContentBlock(
        type="tool_use",
        id=call_id,
        name=mapper.restore(name),
        input=cast(JsonObject, parsed),
    )


def _convert_usage(value: object) -> AnthropicUsage:
    if value is None:
        return AnthropicUsage()
    usage = _mapping(value, "usage")
    total_input = _non_negative_integer(usage, "input_tokens", "usage.input_tokens")
    output = _non_negative_integer(usage, "output_tokens", "usage.output_tokens")

    details_value = usage.get("input_tokens_details")
    if details_value is None:
        details: Mapping[str, Any] = {}
    else:
        details = _mapping(details_value, "usage.input_tokens_details")
    cache_read = _optional_non_negative_integer(
        details, "cached_tokens", "usage.input_tokens_details.cached_tokens"
    )
    cache_creation = _optional_non_negative_integer(
        details,
        "cache_write_tokens",
        "usage.input_tokens_details.cache_write_tokens",
    )
    return AnthropicUsage(
        input_tokens=max(0, total_input - cache_read - cache_creation),
        output_tokens=output,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_creation,
    )


def _required_string(
    value: Mapping[str, Any],
    key: str,
    field_path: str,
    *,
    allow_empty: bool = False,
) -> str:
    candidate = value.get(key)
    if not isinstance(candidate, str) or (not allow_empty and not candidate):
        _fail(field_path, "invalid_response", f"{field_path} must be a string")
    return candidate


def _non_negative_integer(value: Mapping[str, Any], key: str, field_path: str) -> int:
    candidate = value.get(key)
    if not isinstance(candidate, int) or isinstance(candidate, bool) or candidate < 0:
        _fail(field_path, "invalid_usage", f"{field_path} must be a non-negative integer")
    return candidate


def _optional_non_negative_integer(
    value: Mapping[str, Any], key: str, field_path: str
) -> int:
    if key not in value or value[key] is None:
        return 0
    return _non_negative_integer(value, key, field_path)


def _mapping(value: object, field_path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(field_path, "invalid_response", f"{field_path} must be an object")
    return cast(Mapping[str, Any], value)


def _is_server_tool_item(item_type: str) -> bool:
    return item_type.endswith("_call") or item_type.endswith("_result")


def _fail(field_path: str, code: str, message: str) -> Never:
    raise ResponseConversionError(message, code=code, field_path=field_path)


__all__ = [
    "ConvertedResponse",
    "ResponseConversionError",
    "ResponseConversionFact",
    "anthropic_message_id_from_response_id",
    "convert_responses_response_to_anthropic",
]