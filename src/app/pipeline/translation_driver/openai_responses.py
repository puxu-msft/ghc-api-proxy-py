"""OpenAI Responses translators.

`model-translation.md` shows `instructions` as an array of role-bearing objects, and notes we do
not need that flexibility yet. The Copilot upstream does not offer it either: measured on
2026-08-18, it accepts `instructions` only as a string and answers `failed to parse request` to
every array form tried — `[str]`, `[{role, content: str}]`, `[{role, content: [{type: text}]}]`,
the same with `input_text`, and with an explicit `type: message`. So the blocks are joined here.

That costs the per-block `cache_control` on this path, which is why `Conversion` records it rather
than letting it vanish. The Anthropic passthrough path keeps the blocks intact.
"""

from collections.abc import Mapping
from typing import Any, cast

from app.pipeline.translation_driver.semantic import (
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
        source_format=WIRE_FORMAT,
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


def _instructions_value(blocks: list[SystemBlock], request: SemanticRequest) -> str:
    """Join the system blocks into the one shape this upstream accepts.

    Blank-line separated so two blocks do not run into one sentence. Any per-block metadata is
    lost here — `cache_control` in practice — and named rather than dropped in silence.
    """
    dropped = sorted({key for block in blocks for key in block.metadata})
    if dropped:
        request.conversion.record(
            f"system block metadata not carried into {WIRE_FORMAT} instructions: "
            f"{', '.join(dropped)}"
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


def to_openai_responses(request: SemanticRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": request.model, "input": request.messages}
    if request.system:
        payload["instructions"] = _instructions_value(request.system, request)
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
