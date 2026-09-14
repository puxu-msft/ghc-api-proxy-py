"""OpenAI SDK is the wire-format oracle for Responses tests."""

from collections.abc import Mapping
from typing import Any, cast

from openai._utils import maybe_transform
from openai.types.responses import (
    Response,
    ResponseCreateParams,
    ResponseInputItemParam,
    ResponseStreamEvent,
    ToolParam,
)
from pydantic import TypeAdapter

_REQUEST: TypeAdapter[Any] = TypeAdapter(ResponseCreateParams)
_INPUT_ITEM: TypeAdapter[Any] = TypeAdapter(ResponseInputItemParam)
_TOOL: TypeAdapter[Any] = TypeAdapter(ToolParam)
_STREAM_EVENT: TypeAdapter[Any] = TypeAdapter(ResponseStreamEvent)


def validate_responses_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return an SDK-normalized Responses request payload."""
    transformed = cast(
        dict[str, Any],
        maybe_transform(dict(payload), ResponseCreateParams),
    )
    _REQUEST.validate_python(transformed)
    return transformed


def validate_responses_input_item(item: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one SDK Responses input item."""
    return cast(dict[str, Any], _INPUT_ITEM.validate_python(dict(item)))


def validate_responses_tool(tool: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one SDK Responses tool declaration."""
    return cast(dict[str, Any], _TOOL.validate_python(dict(tool)))


def validate_responses_response(payload: Mapping[str, Any]) -> Response:
    """Validate a complete Responses response with the installed SDK."""
    return Response.model_validate(dict(payload))


def validate_responses_stream_event(payload: Mapping[str, Any]) -> Any:
    """Validate one Responses SSE event using the SDK's discriminated union."""
    return _STREAM_EVENT.validate_python(dict(payload))
