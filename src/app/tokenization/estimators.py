import time
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, Literal, cast

import tiktoken
from anyio.to_thread import run_sync

from app.models.anthropic import ContentBlock, MessagesRequest
from app.observability.metrics import RESPONSIVENESS
from app.tokenization.features import TOKENIZER_NAME as _TOKENIZER_NAME
from app.tokenization.features import analyze_responses_input
from app.tokenization.features import count_ordinary as _count_ordinary
from app.tokenization.types import EstimatorTiming, TokenizationCapabilities
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


def _anthropic_structured_tokens(encoding: tiktoken.Encoding, value: object) -> int:
    return _count_ordinary(encoding, dumps(value).decode())


def _anthropic_source_text(source: object) -> Sequence[str]:
    if not isinstance(source, Mapping):
        return ()
    typed_source = cast(Mapping[str, object], source)
    source_type = typed_source.get("type")
    data = typed_source.get("data")
    if source_type == "text" and isinstance(data, str):
        return (data,)
    if source_type == "content":
        content = typed_source.get("content")
        if isinstance(content, str):
            return (content,)
        if isinstance(content, list):
            return tuple(
                part
                for part in (
                    _anthropic_block_text_value(item, include_thinking=True)
                    for item in cast(list[object], content)
                )
                if part is not None
            )
    return ()


def _anthropic_block_text_value(
    block: object,
    *,
    include_thinking: bool,
) -> str | None:
    if not isinstance(block, Mapping):
        return None
    value = cast(Mapping[str, object], block)
    block_type = value.get("type")
    if block_type in {"thinking", "redacted_thinking"} and not include_thinking:
        return None
    text = value.get("text")
    if isinstance(text, str):
        return text
    thinking = value.get("thinking")
    if block_type == "thinking" and isinstance(thinking, str):
        return thinking
    content = value.get("content")
    if isinstance(content, str):
        return content
    return None


def _anthropic_block_tokens(
    encoding: tiktoken.Encoding,
    block: ContentBlock,
    *,
    include_thinking: bool,
    capabilities: TokenizationCapabilities | None,
) -> int:
    total = 4
    if block.text is not None:
        total += _count_ordinary(encoding, block.text)
    if block.type == "thinking":
        if include_thinking and block.thinking is not None:
            total += _count_ordinary(encoding, block.thinking)
        return total
    if block.type == "redacted_thinking":
        return total
    if block.id is not None:
        total += _count_ordinary(encoding, block.id)
    if block.name is not None:
        total += _count_ordinary(encoding, block.name)
    if block.tool_use_id is not None:
        total += _count_ordinary(encoding, block.tool_use_id)
    if block.is_error is not None:
        total += _anthropic_structured_tokens(encoding, block.is_error)
    if block.input is not None:
        total += _anthropic_structured_tokens(encoding, block.input)
    if isinstance(block.content, str):
        total += _count_ordinary(encoding, block.content)
    elif isinstance(block.content, list):
        total += sum(
            _anthropic_block_tokens(
                encoding,
                nested,
                include_thinking=include_thinking,
                capabilities=capabilities,
            )
            for nested in block.content
        )
    for text in _anthropic_source_text(block.source):
        total += _count_ordinary(encoding, text)
    if (
        block.type == "image"
        and capabilities is not None
        and capabilities.visual_formula is not None
    ):
        source: Mapping[str, object] = (
            cast(Mapping[str, object], block.source)
            if isinstance(block.source, Mapping)
            else {}
        )
        extra: Mapping[str, object] = (
            cast(Mapping[str, object], block.model_extra)
            if isinstance(block.model_extra, Mapping)
            else {}
        )
        width = source.get("width", extra.get("width"))
        height = source.get("height", extra.get("height"))
        if type(width) is int and type(height) is int and width >= 0 and height >= 0:
            formula = capabilities.visual_formula
            total += (
                (width + formula.patch_width - 1) // formula.patch_width
                * ((height + formula.patch_height - 1) // formula.patch_height)
            )
    return total


def _anthropic_message_tokens(
    encoding: tiktoken.Encoding,
    content: str | list[ContentBlock],
    *,
    include_thinking: bool,
    capabilities: TokenizationCapabilities | None,
) -> int:
    if isinstance(content, str):
        return _count_ordinary(encoding, content)
    return sum(
        _anthropic_block_tokens(
            encoding,
            block,
            include_thinking=include_thinking,
            capabilities=capabilities,
        )
        for block in content
    )


def estimate_anthropic_input(
    request: MessagesRequest,
    *,
    capabilities: TokenizationCapabilities | None = None,
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
        last_assistant = max(
            (
                index
                for index, message in enumerate(request.messages)
                if message.role == "assistant"
            ),
            default=-1,
        )
        for index, message in enumerate(request.messages):
            total += _count_ordinary(encoding, message.role)
            include_thinking = (
                message.role != "assistant"
                or capabilities is None
                or capabilities.anthropic_thinking_mode == "keep_all"
                or index == last_assistant
            )
            total += _anthropic_message_tokens(
                encoding,
                message.content,
                include_thinking=include_thinking,
                capabilities=capabilities,
            )
            total += 4
        return max(total, 1)


def estimate_responses_input(
    payload: Mapping[str, Any],
    *,
    capabilities: TokenizationCapabilities | None = None,
    timings: list[EstimatorTiming] | None = None,
) -> int:
    """Return the legacy integer view of the structured Responses analysis."""
    return max(
        analyze_responses_input(
            payload,
            capabilities=capabilities,
            timings=timings,
        ).known_tokens,
        1,
    )
