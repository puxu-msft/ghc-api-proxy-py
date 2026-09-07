import time
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from typing import Any, Literal

import tiktoken
from anyio.to_thread import run_sync

from app.models.anthropic import ContentBlock, MessagesRequest
from app.observability.metrics import RESPONSIVENESS
from app.tokenization.features import TOKENIZER_NAME as _TOKENIZER_NAME
from app.tokenization.features import analyze_responses_input
from app.tokenization.features import count_ordinary as _count_ordinary
from app.tokenization.types import EstimatorTiming
from app.wire_json import dumps


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
            total += _count_ordinary(encoding, request.system) + 4
        elif request.system:
            total += sum(_count_ordinary(encoding, block.text) + 4 for block in request.system)
        if request.tools:
            tool_data = [tool.model_dump(mode="json", exclude_none=True) for tool in request.tools]
            total += _count_ordinary(encoding, dumps(tool_data).decode()) + 4
        for message in request.messages:
            total += _count_ordinary(encoding, message.role)
            total += _count_ordinary(
                encoding,
                _anthropic_content_text(
                    message.content,
                    assistant=message.role == "assistant",
                ),
            )
            total += 4
        return max(total, 1)


def estimate_responses_input(
    payload: Mapping[str, Any],
    *,
    timings: list[EstimatorTiming] | None = None,
) -> int:
    """Return the legacy integer view of the structured Responses analysis."""
    return max(analyze_responses_input(payload, timings=timings).known_tokens, 1)
