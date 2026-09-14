"""Command Code NDJSON event assembly.

The upstream stream is line-delimited JSON rather than SSE. The transport
adapter presents one decoded line as ``SseEvent`` to the generic delivery loop;
this assembler is the only place that interprets Command Code event names.
"""

import logging
from typing import Any, cast

from app.errors import STATUS_FOR_CATEGORY, ErrorCategory, ErrorInfo
from app.pipeline.delivery.assembling import (
    FailureOrigin,
    ReplyDialect,
    StreamFailure,
    Terminal,
)
from app.pipeline.delivery.blocks import TEXT, THINKING, TOOL_USE, CompletedBlock
from app.pipeline.delivery.sse_source import SseEvent
from app.pipeline.translation_driver.commandcode import (
    CommandCodeEventAccumulator,
    commandcode_usage_to_anthropic,
    commandcode_usage_to_responses,
)
from app.pipeline.translation_driver.content import BlockKind

logger = logging.getLogger(__name__)


def _category_for_status(status: int) -> ErrorCategory:
    if status == 401:
        return ErrorCategory.AUTH
    if status == 403:
        return ErrorCategory.PERMISSION
    if status == 404:
        return ErrorCategory.NOT_FOUND
    if status in {402, 429}:
        return ErrorCategory.RATE_LIMIT
    if 400 <= status < 500:
        return ErrorCategory.CLIENT
    return ErrorCategory.UPSTREAM


def commandcode_failure_from(event: SseEvent) -> StreamFailure | None:
    data = event.json()
    kind = event.event or str(data.get("type", ""))
    if kind != "error":
        return None
    nested = data.get("error")
    message = ""
    if isinstance(nested, dict):
        message = str(cast(dict[str, Any], nested).get("message") or "")
    if not message:
        message = str(data.get("message") or "Command Code upstream error")
    status = 502
    if message.startswith("<") and ">" in message[:5]:
        try:
            status = int(message[1 : message.index(">")])
        except ValueError:
            status = 502
    category = _category_for_status(status)
    logger.warning("Command Code upstream sent error: %s", message)
    return StreamFailure(
        origin=FailureOrigin.UPSTREAM_EVENT,
        event=kind,
        raw_data=event.data,
        info=ErrorInfo(
            category=category,
            message=message,
            status_code=STATUS_FOR_CATEGORY[category],
            code=kind,
            source_format="commandcode",
            source_bytes=event.data.encode(),
        ),
    )


def _completed_block(index: int, block: Any) -> CompletedBlock:
    if block.kind is BlockKind.TEXT:
        return CompletedBlock(index=index, kind=TEXT, payload={"type": TEXT, "text": block.text})
    if block.kind is BlockKind.REASONING:
        reasoning = block.reasoning
        text = reasoning.visible_text if reasoning is not None else ""
        return CompletedBlock(
            index=index,
            kind=THINKING,
            payload={"type": THINKING, "thinking": text},
            reasoning=reasoning,
        )
    return CompletedBlock(
        index=index,
        kind=TOOL_USE,
        payload={
            "type": TOOL_USE,
            "id": block.call_id,
            "name": block.name,
            "input": block.arguments if block.arguments is not None else {},
        },
    )


class CommandCodeAssembler:
    def __init__(self) -> None:
        self._accumulator = CommandCodeEventAccumulator()
        self._next_index = 0
        self._terminal = Terminal(dialect=ReplyDialect.COMMANDCODE)
        self._failure: StreamFailure | None = None

    @property
    def terminal(self) -> Terminal:
        return self._terminal

    @property
    def failure(self) -> StreamFailure | None:
        return self._failure

    @property
    def queued_bytes(self) -> int:
        return 0

    @property
    def cut_mid_block(self) -> bool:
        return self._accumulator.cut_mid_block

    def close(self) -> tuple[CompletedBlock, ...]:
        self._accumulator.finish()
        if (
            self._failure is None
            and not self._terminal.seen
            and self._terminal.blocks == 0
        ):
            self._failure = _proxy_failure(
                message="Command Code stream ended without a terminal event or complete output",
                code="commandcode_incomplete_stream",
            )
        return ()

    def push(self, event: SseEvent) -> tuple[CompletedBlock, ...]:
        failure = commandcode_failure_from(event)
        if failure is not None:
            self._failure = failure
            return ()
        data = event.json()
        if not data:
            return ()
        completed = self._convert(self._accumulator.push(data))
        kind = event.event or str(data.get("type", ""))
        if kind == "finish":
            self._terminal.seen = True
            self._terminal.stop_reason = self._accumulator.stop_reason or "end_turn"
            self._terminal.usage = (
                commandcode_usage_to_anthropic(self._accumulator.usage)
                if self._accumulator.usage_seen
                else {}
            )
            self._terminal.upstream_usage = commandcode_usage_to_responses(
                self._accumulator.usage
            )
            if not self._terminal.blocks:
                self._failure = _proxy_failure(
                    message="Command Code returned no output",
                    code="commandcode_empty_output",
                )
            elif not self._accumulator.output_tokens_seen:
                self._failure = _proxy_failure(
                    message="Command Code returned no usage",
                    code="commandcode_missing_usage",
                )
            elif self._accumulator.output_tokens == 0:
                self._failure = _proxy_failure(
                    message="Command Code returned zero output tokens",
                    code="commandcode_zero_output",
                )
        elif kind == "finish-step":
            self._terminal.usage = (
                commandcode_usage_to_anthropic(self._accumulator.usage)
                if self._accumulator.usage_seen
                else {}
            )
            self._terminal.upstream_usage = commandcode_usage_to_responses(
                self._accumulator.usage
            )
        return completed

    def _convert(self, blocks: tuple[Any, ...]) -> tuple[CompletedBlock, ...]:
        converted: list[CompletedBlock] = []
        for block in blocks:
            completed = _completed_block(self._next_index, block)
            self._next_index += 1
            self._terminal.record(completed)
            converted.append(completed)
        return tuple(converted)


def _proxy_failure(*, message: str, code: str) -> StreamFailure:
    return StreamFailure(
        origin=FailureOrigin.PROXY_REFUSAL,
        event="error",
        raw_data="",
        info=ErrorInfo(
            category=ErrorCategory.UPSTREAM,
            message=message,
            status_code=STATUS_FOR_CATEGORY[ErrorCategory.UPSTREAM],
            code=code,
            source_format="commandcode",
        ),
    )
