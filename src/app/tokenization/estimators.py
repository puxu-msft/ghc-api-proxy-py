import time
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal, cast

import tiktoken
from anyio.to_thread import run_sync

from app.models.anthropic import ContentBlock, MessagesRequest
from app.observability.metrics import RESPONSIVENESS
from app.wire_json import dumps

_TOKENIZER_NAME = "o200k_base"


@dataclass(frozen=True, slots=True)
class EstimatorTiming:
    format: Literal["anthropic", "responses"]
    phase: Literal["lookup", "estimate"]
    seconds: float
    failed: bool


@contextmanager
def _measure(
    format_name: Literal["anthropic", "responses"],
    phase: Literal["lookup", "estimate"],
    timings: list[EstimatorTiming] | None,
) -> Generator[None]:
    if timings is None:
        with RESPONSIVENESS.tokenizer[(format_name, phase)].measure():
            yield
        return
    # A child process returns these observations to the parent rather than updating a registry the HTTP metrics endpoint cannot see.
    started = time.monotonic()
    failed = True
    try:
        yield
        failed = False
    finally:
        timings.append(EstimatorTiming(format_name, phase, time.monotonic() - started, failed))


async def preload_tokenizer() -> None:
    await run_sync(tiktoken.get_encoding, _TOKENIZER_NAME)


def _anthropic_content_text(
    content: str | list[ContentBlock],
    *,
    assistant: bool,
) -> str:
    if isinstance(content, str):
        return content
    values: list[str] = []
    for block in content:
        if assistant and block.type in ("thinking", "redacted_thinking"):
            continue
        if block.text is not None:
            values.append(block.text)
        elif block.content is not None:
            values.append(
                block.content
                if isinstance(block.content, str)
                else dumps(
                    [item.model_dump(mode="json", exclude_none=True) for item in block.content]
                ).decode()
            )
        elif block.input is not None:
            values.append(dumps(block.input).decode())
        elif block.source is not None:
            values.append(dumps(block.source).decode())
    return "\n".join(values)


def estimate_anthropic_input(
    request: MessagesRequest,
    *,
    timings: list[EstimatorTiming] | None = None,
) -> int:
    with _measure("anthropic", "lookup", timings):
        encoding = tiktoken.get_encoding(_TOKENIZER_NAME)
    with _measure("anthropic", "estimate", timings):
        total = 0
        if isinstance(request.system, str):
            total += len(encoding.encode(request.system)) + 4
        elif request.system:
            total += sum(len(encoding.encode(block.text)) + 4 for block in request.system)
        if request.tools:
            tool_data = [tool.model_dump(mode="json", exclude_none=True) for tool in request.tools]
            total += len(encoding.encode(dumps(tool_data).decode())) + 4
        for message in request.messages:
            total += len(encoding.encode(message.role))
            total += len(
                encoding.encode(
                    _anthropic_content_text(
                        message.content,
                        assistant=message.role == "assistant",
                    )
                )
            )
            total += 4
        return max(total, 1)


def _responses_item_text(item: Mapping[str, Any]) -> str:
    """What one `input` item contributes, as text.

    Every item contributes something. The first draft skipped `reasoning`, mirroring the Anthropic estimator's treatment of `thinking`, on the reasoning that calibration would absorb whatever upstream really charges. That was wrong twice over: nothing teaches this protocol's calibration yet, so there is nothing absorbing anything, and a reasoning item is not small — a measured round trip carried 7286 characters of `encrypted_content` in one, and the 7.6 KB body it belonged to was reported as 30 tokens.

    Whether upstream bills for that payload is still not measurable from here; the OpenAI family publishes no count endpoint to ask. But zero is measurably wrong for what the number is used for, and it is wrong in the direction that gets a request refused after it was said to fit.

    An item of a kind not listed falls back to its whole JSON, for the same reason.
    """
    kind = item.get("type")
    if kind == "message":
        content = item.get("content")
        parts: list[str] = []
        role = item.get("role")
        if isinstance(role, str):
            parts.append(role)
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for part in cast(list[Any], content):
                if not isinstance(part, dict):
                    parts.append(dumps(part).decode())
                    continue
                entry = cast(dict[str, Any], part)
                text = entry.get("text")
                parts.append(text if isinstance(text, str) else dumps(entry).decode())
        elif content is not None:
            parts.append(dumps(content).decode())
        return "\n".join(parts)
    if kind == "function_call":
        return "\n".join(
            str(item[key]) for key in ("call_id", "name", "arguments") if item.get(key) is not None
        )
    if kind == "function_call_output":
        output = item.get("output")
        return "\n".join(
            [
                *([str(item["call_id"])] if item.get("call_id") is not None else []),
                output if isinstance(output, str) else dumps(output).decode(),
            ]
        )
    return dumps(item).decode()


def estimate_responses_input(
    payload: Mapping[str, Any],
    *,
    timings: list[EstimatorTiming] | None = None,
) -> int:
    """Estimate the input tokens of an OpenAI Responses body.

    Reads the wire dict rather than a typed model, because this runs on a body the translator has just produced and the translator's output shape is the thing being measured. A model in between would have to be kept in step with it to say anything true.

    Upstream has no counter to check this against: the OpenAI family reports usage only on a finished response. So the number is an estimate in a stronger sense than the Anthropic one, which at least shares a caliber with an endpoint that answers — and, until something teaches this protocol's calibration, an *uncorrected* one. Calibration is keyed on the target protocol all the same, because mixing the two families' factors would correct each with the other's error.
    """
    with _measure("responses", "lookup", timings):
        encoding = tiktoken.get_encoding(_TOKENIZER_NAME)
    with _measure("responses", "estimate", timings):
        total = 0
        instructions = payload.get("instructions")
        if isinstance(instructions, str) and instructions:
            total += len(encoding.encode(instructions)) + 4
        tools = payload.get("tools")
        if tools:
            total += len(encoding.encode(dumps(tools).decode())) + 4
        items = payload.get("input")
        if isinstance(items, list):
            for item in cast(list[Any], items):
                if not isinstance(item, dict):
                    total += len(encoding.encode(dumps(item).decode())) + 4
                    continue
                text = _responses_item_text(cast(dict[str, Any], item))
                if text:
                    total += len(encoding.encode(text)) + 4
        return max(total, 1)
