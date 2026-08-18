"""Anthropic Messages translators."""

from collections.abc import Mapping
from typing import Any, cast

from app.pipeline.translation_driver.semantic import (
    SemanticRequest,
    SystemBlock,
    system_blocks_from_value,
)

WIRE_FORMAT = "anthropic-messages"

_PASSTHROUGH_KEYS = frozenset(
    {"model", "system", "messages", "tools", "stream", "max_tokens", "temperature"}
)


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries = cast(list[object], value)
    return [dict[str, Any](cast(Mapping[str, Any], e)) for e in entries if isinstance(e, Mapping)]


def from_anthropic_messages(payload: Mapping[str, Any]) -> SemanticRequest:
    blocks, problem = system_blocks_from_value(payload.get("system"))
    model = payload.get("model")
    request = SemanticRequest(
        model=model if isinstance(model, str) else "",
        system=blocks,
        messages=_dict_list(payload.get("messages")),
        tools=_dict_list(payload.get("tools")),
        stream=bool(payload.get("stream", False)),
        source_format=WIRE_FORMAT,
    )
    if problem is not None:
        request.conversion.record(problem)

    max_tokens = payload.get("max_tokens")
    if isinstance(max_tokens, int):
        request.max_output_tokens = max_tokens
    temperature = payload.get("temperature")
    if isinstance(temperature, int | float):
        request.temperature = float(temperature)

    # Anything not claimed above is carried rather than dropped.
    # An unmodelled field therefore survives the round trip back to the same format.
    request.extensions = {
        key: value for key, value in payload.items() if key not in _PASSTHROUGH_KEYS
    }
    return request


def _system_value(blocks: list[SystemBlock]) -> list[dict[str, Any]]:
    return [{"type": "text", "text": block.text, **dict(block.metadata)} for block in blocks]


def to_anthropic_messages(request: SemanticRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": request.model, "messages": request.messages}
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
