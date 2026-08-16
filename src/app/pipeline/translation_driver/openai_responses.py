"""OpenAI Responses translators.

`model-translation.md`: Anthropic carries the system prompt in a top-level `system` array.
Responses carries it in a top-level `instructions` array of objects with `role` and `content`.
Responses has the richer shape, which we do not need yet, so one system entry carries the blocks.
"""

from collections.abc import Mapping
from typing import Any, cast

from app.pipeline.translation_driver.semantic import (
    SemanticRequest,
    SystemBlock,
    system_blocks_from_value,
)

_PASSTHROUGH_KEYS = frozenset(
    {"model", "instructions", "input", "tools", "stream", "max_output_tokens", "temperature"}
)
SYSTEM_ROLE = "system"


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries = cast(list[object], value)
    return [dict[str, Any](cast(Mapping[str, Any], e)) for e in entries if isinstance(e, Mapping)]


def _blocks_from_instructions(value: object) -> tuple[list[SystemBlock], str | None]:
    """Read `instructions`, which may be a string or role-bearing entries."""
    if isinstance(value, str) or value is None:
        return system_blocks_from_value(value)
    if not isinstance(value, list):
        return [], "instructions is neither a string nor a list"

    blocks: list[SystemBlock] = []
    problem: str | None = None
    for entry in cast(list[object], value):
        if not isinstance(entry, Mapping):
            problem = "instructions entry is not an object"
            continue
        item = cast(Mapping[str, Any], entry)
        role = item.get("role")
        if role is not None and role != SYSTEM_ROLE:
            # Roles other than system are part of the richer shape we do not use yet.
            problem = f"instructions role {role!r} is not carried"
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
        messages=_dict_list(payload.get("input")),
        tools=_dict_list(payload.get("tools")),
        stream=bool(payload.get("stream", False)),
    )
    if problem is not None:
        request.conversion.record(problem)

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


def to_openai_responses(request: SemanticRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": request.model, "input": request.messages}
    if request.system:
        content = [
            {"type": "text", "text": block.text, **dict(block.metadata)}
            for block in request.system
        ]
        payload["instructions"] = [{"role": SYSTEM_ROLE, "content": content}]
    if request.tools:
        payload["tools"] = request.tools
    if request.stream:
        payload["stream"] = True
    if request.max_output_tokens is not None:
        payload["max_output_tokens"] = request.max_output_tokens
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    payload.update(request.extensions)
    return payload
