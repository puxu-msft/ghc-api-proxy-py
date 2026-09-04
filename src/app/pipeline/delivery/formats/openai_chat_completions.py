"""The assembler for a Chat Completions upstream.

The third assembler, beside the Anthropic and Responses ones. A `chat.completion.chunk`
stream has no block-boundary events at all — every boundary is a decision this module
makes: text ends when a different kind of delta arrives, a tool call ends when a new
tool index opens or the finish reason lands. That is the price of the format, not a
choice this file got to make; what it did choose is that a draft still open when the
stream stops is *flushed* rather than dropped, because chat text is append-only and a
torn stream's text is as complete as upstream will ever declare it.

The request-side translator this leg pairs with lives in
`app.pipeline.translation_driver.openai_chat_completions`, which owns the shared
mappings (stop reasons, usage) imported here — the buffered and streaming halves of
one leg answer those questions once.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, cast

from app.errors import STATUS_FOR_CATEGORY, ErrorCategory, ErrorInfo
from app.pipeline.delivery.assembling import FailureOrigin, ReplyDialect, StreamFailure, Terminal
from app.pipeline.delivery.blocks import TEXT, THINKING, TOOL_USE, CompletedBlock
from app.pipeline.delivery.sse_source import SseEvent
from app.pipeline.translation_driver.openai_chat_completions import (
    CHAT_STOP_REASONS,
    REASONING_CONTENT,
    WIRE_FORMAT,
    chat_usage_to_anthropic,
)

_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _Draft:
    """One block being accumulated, in Anthropic's block vocabulary."""

    index: int
    kind: str
    payload: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    text: str = ""
    partial_json: str = ""


class ChatCompletionsAssembler:
    """Assembles blocks from a `chat.completion.chunk` SSE stream."""

    def __init__(self) -> None:
        self._next_index = 0
        self._open: dict[int, _Draft] = {}
        # The one open text and thinking draft each, by Anthropic block index; a
        # second delta of the same kind continues rather than reopens. Tool drafts
        # are keyed separately, chat tool index → block index.
        self._text: int | None = None
        self._thinking: int | None = None
        self._tools: dict[int, int] = {}
        self._terminal = Terminal(dialect=ReplyDialect.CHAT_COMPLETIONS)
        self._failure: StreamFailure | None = None

    @property
    def terminal(self) -> Terminal:
        return self._terminal

    @property
    def failure(self) -> StreamFailure | None:
        return self._failure

    def close(self) -> tuple[CompletedBlock, ...]:
        """Flush what is still open.

        The opposite of the boundary-format assemblers, deliberately. Anthropic and
        Responses both announce a block's end, so what their close finds open is a
        half-built block that every ending drops. Chat announces nothing: the text
        in an open draft arrived complete as deltas, and only the *ending* is
        missing — which the unterminated-stop-reason machinery already tells the
        client about.
        """
        return self._flush_open()

    @property
    def queued_bytes(self) -> int:
        """Zero, and see `BlockAssembler.queued_bytes` for why that is the pre-existing accounting."""
        return 0

    @property
    def cut_mid_block(self) -> bool:
        """A draft still open means the events stopped part-way through a block. See `BlockAssembler`."""
        return bool(self._open)

    def push(self, event: SseEvent) -> tuple[CompletedBlock, ...]:
        if event.data.strip() == "[DONE]":
            # The transport's own terminator. `finish_reason` is what sets `seen`
            # normally; a [DONE] without one still means upstream ended on purpose.
            self._terminal.seen = True
            return self._flush_open()
        data = event.json()
        if not data:
            return ()
        if "error" in data and "choices" not in data:
            # Some OpenAI-compatible backends report a failed turn as a bare error
            # object mid-stream. Carried rather than logged and dropped, so the
            # client is told the turn failed instead of watching a 200 end early.
            self._failure = chat_failure_from(event)
            return ()
        completed: list[CompletedBlock] = []
        usage = data.get("usage")
        if isinstance(usage, dict) and usage:
            # Anthropic keys: the terminal is rendered by whichever framer the
            # client leg picked, and every framer reads this record the same way.
            self._terminal.usage = chat_usage_to_anthropic(cast(dict[str, Any], usage))
        choices = data.get("choices")
        if isinstance(choices, list):
            for choice in cast(list[object], choices):
                if isinstance(choice, dict):
                    completed.extend(
                        self._push_choice(dict[str, Any](cast(dict[str, Any], choice)))
                    )
        return tuple(completed)

    def _push_choice(self, choice: dict[str, Any]) -> tuple[CompletedBlock, ...]:
        completed: list[CompletedBlock] = []
        delta = dict[str, Any]()
        if isinstance(choice.get("delta"), dict):
            delta = dict[str, Any](cast(dict[str, Any], choice["delta"]))
        if delta:
            reasoning = delta.get(REASONING_CONTENT)
            if isinstance(reasoning, str) and reasoning:
                completed.extend(self._close_kind(TEXT))
                completed.extend(
                    self._accumulate(self._ensure_thinking(), THINKING, reasoning)
                )
            content = delta.get("content")
            if isinstance(content, str) and content:
                completed.extend(self._close_kind(THINKING))
                completed.extend(self._accumulate(self._ensure_text(), TEXT, content))
            raw_calls = delta.get("tool_calls")
            if isinstance(raw_calls, list):
                for call in cast(list[object], raw_calls):
                    if isinstance(call, dict):
                        completed.extend(
                            self._push_tool_call(dict[str, Any](cast(dict[str, Any], call)))
                        )
        finish = choice.get("finish_reason")
        if isinstance(finish, str) and finish:
            completed.extend(self._flush_open())
            self._terminal.stop_reason = CHAT_STOP_REASONS.get(finish, finish)
            self._terminal.seen = True
        return tuple(completed)

    def _push_tool_call(self, call: dict[str, Any]) -> tuple[CompletedBlock, ...]:
        chat_index = call.get("index", 0)
        if not isinstance(chat_index, int) or isinstance(chat_index, bool):
            chat_index = 0
        function = dict[str, Any]()
        if isinstance(call.get("function"), dict):
            function = dict[str, Any](cast(dict[str, Any], call["function"]))
        if chat_index not in self._tools:
            # A new tool index ends the previous one: chat streams tool calls one
            # index at a time, and the index is the only boundary the format gives.
            # A tool call after prose ends the prose for the same reason.
            completed = [*self._close_kind(TEXT), *self._close_kind(THINKING), *self._close_tools()]
            draft = _Draft(
                index=self._take_index(),
                kind=TOOL_USE,
                payload={
                    "type": TOOL_USE,
                    "id": str(call.get("id", "")),
                    "name": str(function.get("name", "")),
                },
            )
            self._open[draft.index] = draft
            self._tools[chat_index] = draft.index
            self._accumulate(draft.index, TOOL_USE, str(function.get("arguments", "") or ""))
            return tuple(completed)
        block_index = self._tools[chat_index]
        if isinstance(call.get("id"), str) and call["id"]:
            self._open[block_index].payload["id"] = call["id"]
        if isinstance(function.get("name"), str) and function["name"]:
            self._open[block_index].payload["name"] = function["name"]
        self._accumulate(block_index, TOOL_USE, str(function.get("arguments", "") or ""))
        return ()

    def _ensure_text(self) -> int:
        if self._text is None:
            draft = _Draft(index=self._take_index(), kind=TEXT, payload={"type": TEXT})
            self._open[draft.index] = draft
            self._text = draft.index
        return self._text

    def _ensure_thinking(self) -> int:
        if self._thinking is None:
            draft = _Draft(index=self._take_index(), kind=THINKING, payload={"type": THINKING})
            self._open[draft.index] = draft
            self._thinking = draft.index
        return self._thinking

    def _accumulate(self, block_index: int, kind: str, piece: str) -> tuple[CompletedBlock, ...]:
        if not piece:
            return ()
        draft = self._open.get(block_index)
        if draft is None:
            return ()
        if kind == TOOL_USE:
            draft.partial_json += piece
        else:
            draft.text += piece
        return ()

    def _close_kind(self, kind: str) -> tuple[CompletedBlock, ...]:
        """Close the singleton draft of one kind, if it is open."""
        if kind == TEXT:
            index, self._text = self._text, None
        elif kind == THINKING:
            index, self._thinking = self._thinking, None
        else:
            return ()
        return self._close(index) if index is not None else ()

    def _close_tools(self) -> tuple[CompletedBlock, ...]:
        completed: list[CompletedBlock] = []
        for block_index in list(self._tools.values()):
            completed.extend(self._close(block_index))
        self._tools.clear()
        return tuple(completed)

    def _close(self, index: int) -> tuple[CompletedBlock, ...]:
        draft = self._open.pop(index, None)
        if draft is None:
            return ()
        payload = dict(draft.payload)
        if draft.kind == TEXT:
            payload[TEXT] = draft.text
        elif draft.kind == THINKING:
            payload[THINKING] = draft.text
        elif draft.kind == TOOL_USE and draft.partial_json:
            payload["input"] = _decode_arguments(draft.partial_json)
        block = CompletedBlock(index=draft.index, kind=draft.kind, payload=payload)
        self._terminal.record(block)
        return (block,)

    def _flush_open(self) -> tuple[CompletedBlock, ...]:
        """Close every open draft — text, thinking and tools — in index order."""
        completed: list[CompletedBlock] = []
        for index in sorted(self._open):
            completed.extend(self._close(index))
        self._text = None
        self._thinking = None
        self._tools.clear()
        return tuple(completed)

    def _take_index(self) -> int:
        index = self._next_index
        self._next_index += 1
        return index


def _decode_arguments(partial_json: str) -> dict[str, Any]:
    """A tool call's accumulated argument fragments as an input object.

    Decoded once, at block close, exactly as the Anthropic assembler decodes its
    `input_json_delta`. Fragments that never formed legal JSON — which on this leg
    means the stream stopped inside the call — become an empty input, and the log
    says so: an input nobody can read is worse silent than wrong, and there is no
    client-facing loss record on a streaming leg's drafts.
    """
    try:
        decoded = cast(object, json.loads(partial_json))
    except ValueError:
        _logger.warning("upstream tool call arguments stopped mid-JSON; sent as an empty input")
        return {}
    return cast(dict[str, Any], decoded) if isinstance(decoded, dict) else {}


def chat_failure_from(event: SseEvent) -> StreamFailure | None:
    """A chat upstream's mid-stream error object as a failure record, or None."""
    data = event.json()
    raw = data.get("error")
    detail = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    spelled = str(detail.get("code", "") or detail.get("type", ""))
    message = str(detail.get("message", "")) or "upstream reported a failure"
    return StreamFailure(
        origin=FailureOrigin.UPSTREAM_EVENT,
        event="error",
        raw_data=event.data,
        info=ErrorInfo(
            category=ErrorCategory.UPSTREAM,
            message=message,
            status_code=STATUS_FOR_CATEGORY[ErrorCategory.UPSTREAM],
            code=spelled or "upstream_error_event",
            source_format=WIRE_FORMAT,
            source_bytes=event.data.encode(),
        ),
    )
