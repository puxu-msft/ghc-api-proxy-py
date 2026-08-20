"""Assembling upstream SSE events into complete blocks.

A block is emitted when its closing event arrives, never on a delta.
The assembler is what makes "complete block" a fact rather than a hope.

Two upstream shapes are handled, matching the two protocol legs.
Both produce the same `CompletedBlock`, so delivery never learns which upstream a block is from.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, cast

import orjson

from app.pipeline.delivery.blocks import CompletedBlock
from app.pipeline.delivery.sse_source import SseEvent
from app.pipeline.translation_driver.reasoning_carrier import encode_reasoning_carrier
from app.protocols.responses_anthropic import (
    ResponseConversionError,
    anthropic_usage_from_responses,
)

TEXT = "text"
THINKING = "thinking"
TOOL_USE = "tool_use"


class ReplyDialect(StrEnum):
    """Whose vocabulary the reply arrived in.

    Not `WireFormat`. That enum is the whole taxonomy of body shapes a route can take, and it lives with `RequestContext`, which now holds one of these records — importing it here would close a cycle. What a summary of a reply needs is narrower anyway: only which of the two upstreams described it, so the words on the console line can be that upstream's own. A reply is assembled by exactly one of them, so this is a property of the record rather than something a reader has to be told separately.
    """

    ANTHROPIC = "anthropic"
    RESPONSES = "responses"


@dataclass(slots=True)
class Terminal:
    """What the upstream said when it finished."""

    stop_reason: str = "end_turn"
    usage: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    seen: bool = False
    # Which upstream described this reply, and so which words the console line should use for it. Anthropic by default because that is also the shape a translated reply is read back in.
    dialect: ReplyDialect = ReplyDialect.ANTHROPIC
    # Every tool the model asked for, in the order it asked, duplicates kept. `tool_use` on its own says a turn ended in tool calls; which tools, and how many of each, is the part that tells one turn from another when reading a log.
    tools: list[str] = field(default_factory=lambda: list[str]())
    # Thinking blocks by kind: `txt` carried readable reasoning, `enc` carried only an opaque signature. The distinction is the interesting one — a turn that reasoned and a turn that was handed back sealed reasoning cost the same tokens and look identical from the outside.
    thinking: list[str] = field(default_factory=lambda: list[str]())

    def record(self, block: CompletedBlock) -> None:
        """Take one finished block into the running summary of the reply.

        Classification lives here, on the record itself, rather than at each place a block becomes final. There are three such places — the two assemblers and a buffered reply read back whole — and when each did its own classifying, the same question ("was this reasoning readable?") was answered by three separate expressions that were free to drift apart. Reading the block's own payload, rather than whatever local draft produced it, is what lets one implementation serve all three.
        """
        if block.kind == TOOL_USE:
            self.tools.append(str(block.payload.get("name", "")))
        elif block.kind == THINKING:
            self.thinking.append("txt" if block.payload.get(THINKING) else "enc")


def terminal_from_anthropic(
    body: dict[str, Any], blocks: Iterable[CompletedBlock], *, dialect: ReplyDialect = ReplyDialect.ANTHROPIC
) -> Terminal:
    """The same summary, for a reply that arrived whole instead of in events.

    A buffered request never runs an assembler, so without this the facts a finished reply carries — which tools were asked for, how much reasoning came back, what it cost — had to be dug back out of the response payload at whatever place happened to want them. That is how the same reply came to be described by two different pieces of code, and why only one of them was ever fixed when the description was wrong.

    Reads an **Anthropic-shaped** body. It has no way to notice one that is not, so a caller holding some other shape must not reach for this — `handler.reply_summary` is where that decision is made.

    `seen` is true by construction: a body read whole is a reply that finished, which is exactly what the flag means on the streaming side.

    The stop reason starts empty rather than at the class default. A stream that never sent its terminal event still has a reason to be called `end_turn` by the code that synthesises one; a body simply not carrying the field means nobody said, and printing `end_turn` there would claim a clean finish on no evidence at all.
    """
    terminal = Terminal(seen=True, dialect=dialect, stop_reason="")
    stop_reason = body.get("stop_reason")
    if isinstance(stop_reason, str) and stop_reason:
        terminal.stop_reason = stop_reason
    usage = body.get("usage")
    if isinstance(usage, dict):
        terminal.usage = dict[str, Any](cast(dict[str, Any], usage))
    for block in blocks:
        terminal.record(block)
    return terminal


class BlockAssembler(Protocol):
    def push(self, event: SseEvent) -> tuple[CompletedBlock, ...]:
        """Take one event; return blocks that just became complete."""
        ...

    @property
    def terminal(self) -> Terminal: ...


@dataclass(slots=True)
class _Draft:
    index: int
    kind: str
    payload: dict[str, Any]
    text: str = ""
    partial_json: str = ""


class AnthropicAssembler:
    """Assembles blocks from an Anthropic SSE stream."""

    def __init__(self) -> None:
        self._drafts: dict[int, _Draft] = {}
        self._terminal = Terminal()

    @property
    def terminal(self) -> Terminal:
        return self._terminal

    def push(self, event: SseEvent) -> tuple[CompletedBlock, ...]:
        data = event.json()
        kind = event.event or str(data.get("type", ""))

        if kind == "content_block_start":
            self._open(data)
            return ()
        if kind == "content_block_delta":
            self._accumulate(data)
            return ()
        if kind == "content_block_stop":
            return self._close(data)
        if kind == "message_delta":
            self._read_terminal(data)
            return ()
        if kind == "message_stop":
            self._terminal.seen = True
            return ()
        return ()

    def _open(self, data: dict[str, Any]) -> None:
        index = int(data.get("index", len(self._drafts)))
        raw = data.get("content_block")
        block = dict[str, Any](cast(dict[str, Any], raw)) if isinstance(raw, dict) else {}
        self._drafts[index] = _Draft(
            index=index,
            kind=str(block.get("type", "")),
            payload=block,
        )

    def _accumulate(self, data: dict[str, Any]) -> None:
        index = int(data.get("index", -1))
        draft = self._drafts.get(index)
        if draft is None:
            return
        raw = data.get("delta")
        delta = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
        delta_type = str(delta.get("type", ""))
        if delta_type == "text_delta":
            draft.text += str(delta.get(TEXT, ""))
        elif delta_type == "thinking_delta":
            draft.text += str(delta.get(THINKING, ""))
        elif delta_type == "input_json_delta":
            draft.partial_json += str(delta.get("partial_json", ""))
        elif delta_type == "signature_delta":
            draft.payload["signature"] = str(delta.get("signature", ""))

    def _close(self, data: dict[str, Any]) -> tuple[CompletedBlock, ...]:
        index = int(data.get("index", -1))
        draft = self._drafts.pop(index, None)
        if draft is None:
            return ()
        payload = dict(draft.payload)
        if draft.kind == TEXT:
            payload[TEXT] = draft.text
        elif draft.kind == THINKING:
            payload[THINKING] = draft.text
        elif draft.kind == TOOL_USE and draft.partial_json:
            payload["input"] = _decode_json(draft.partial_json)
        block = CompletedBlock(index=draft.index, kind=draft.kind, payload=payload)
        self._terminal.record(block)
        return (block,)

    def _read_terminal(self, data: dict[str, Any]) -> None:
        raw = data.get("delta")
        delta = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
        reason = delta.get("stop_reason")
        if isinstance(reason, str):
            self._terminal.stop_reason = reason
        usage = data.get("usage")
        if isinstance(usage, dict):
            self._terminal.usage = dict[str, Any](cast(dict[str, Any], usage))


class ResponsesAssembler:
    """Assembles blocks from an OpenAI Responses SSE stream.

    An output item is the unit that closes.
    A block therefore completes on `output_item.done`, not on the deltas that preceded it.
    """

    def __init__(self) -> None:
        self._drafts: dict[str, _Draft] = {}
        self._order = 0
        self._terminal = Terminal(dialect=ReplyDialect.RESPONSES)
        self._saw_tool_call = False

    @property
    def terminal(self) -> Terminal:
        return self._terminal

    def push(self, event: SseEvent) -> tuple[CompletedBlock, ...]:
        data = event.json()
        kind = event.event or str(data.get("type", ""))

        if kind == "response.output_item.added":
            self._open(data)
            return ()
        if kind in {"response.output_text.delta", "response.reasoning_summary_text.delta"}:
            self._accumulate(data, str(data.get("delta", "")))
            return ()
        if kind == "response.function_call_arguments.delta":
            self._accumulate_arguments(data, str(data.get("delta", "")))
            return ()
        if kind == "response.output_item.done":
            return self._close(data)
        if kind in {"response.completed", "response.incomplete"}:
            self._read_terminal(kind, data)
            return ()
        return ()

    def _item_key(self, data: dict[str, Any]) -> str:
        """Which draft an event belongs to.

        `output_index` first, because it is the only identifier this upstream keeps stable: Copilot
        sends a *different* `item.id` on `output_item.added` and `output_item.done` for the same
        item, so keying on the id meant `_close` never found what `_open` had created and the whole
        response assembled into nothing. The ids are kept as a fallback for upstreams that omit the
        index; between the two, only the index is load-bearing.
        """
        index = data.get("output_index")
        if index is not None:
            return f"index:{index}"
        raw = data.get("item")
        if isinstance(raw, dict):
            item = cast(dict[str, Any], raw)
            return str(item.get("id") or data.get("item_id") or "")
        return str(data.get("item_id") or "")

    def _open(self, data: dict[str, Any]) -> None:
        raw = data.get("item")
        item = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
        item_type = str(item.get("type", ""))
        kind = {
            "message": TEXT,
            "function_call": TOOL_USE,
            "reasoning": THINKING,
        }.get(item_type, item_type)
        key = self._item_key(data)
        self._drafts[key] = _Draft(index=self._order, kind=kind, payload=dict(item))
        self._order += 1

    def _accumulate(self, data: dict[str, Any], delta: str) -> None:
        draft = self._drafts.get(self._item_key(data))
        if draft is not None:
            draft.text += delta

    def _accumulate_arguments(self, data: dict[str, Any], delta: str) -> None:
        draft = self._drafts.get(self._item_key(data))
        if draft is not None:
            draft.partial_json += delta

    def _close(self, data: dict[str, Any]) -> tuple[CompletedBlock, ...]:
        key = self._item_key(data)
        draft = self._drafts.pop(key, None)
        if draft is None:
            return ()
        if draft.kind == TOOL_USE:
            self._saw_tool_call = True
            payload: dict[str, Any] = {
                "type": TOOL_USE,
                "id": str(draft.payload.get("call_id") or draft.payload.get("id", "")),
                "name": str(draft.payload.get("name", "")),
                "input": _decode_json(draft.partial_json or "{}"),
            }
        elif draft.kind == THINKING:
            payload = {
                "type": THINKING,
                THINKING: draft.text,
                "signature": _reasoning_signature(draft, data),
            }
        else:
            payload = {"type": TEXT, TEXT: draft.text}
        block = CompletedBlock(index=draft.index, kind=draft.kind, payload=payload)
        self._terminal.record(block)
        return (block,)

    def _read_terminal(self, kind: str, data: dict[str, Any]) -> None:
        self._terminal.seen = True
        raw = data.get("response")
        response = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
        usage = response.get("usage")
        if isinstance(usage, dict):
            self._terminal.usage = _anthropic_usage(cast(dict[str, Any], usage))
        if kind == "response.incomplete":
            details = response.get("incomplete_details")
            reason = ""
            if isinstance(details, dict):
                reason = str(cast(dict[str, Any], details).get("reason", ""))
            # spec.md: the output-token limit is max_tokens downstream.
            self._terminal.stop_reason = (
                "max_tokens" if reason == "max_output_tokens" else "end_turn"
            )
            return
        self._terminal.stop_reason = TOOL_USE if self._saw_tool_call else "end_turn"


def _reasoning_signature(draft: _Draft, closing: dict[str, Any]) -> str:
    """The carrier for a Responses reasoning item, read from the event that closed it.

    `spec.md` fixes both halves: a non-empty `encrypted_content` must survive value-exact so the
    client can echo it back and the next turn can carry on, and a missing or empty one still emits
    the project's bare marker rather than nothing. This used to write `""`, which broke both.

    Read from the closing item rather than the draft: `output_item.added` and `output_item.done`
    do not carry the same content — that is the same asymmetry that made the assembler pair
    nothing when it keyed drafts on `item.id`. The draft is the fallback, not the source.
    """
    raw = closing.get("item")
    item = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    encrypted = str(item.get("encrypted_content", "")) or str(
        draft.payload.get("encrypted_content", "")
    )
    return encode_reasoning_carrier(encrypted or None)


def _anthropic_usage(usage: dict[str, Any]) -> dict[str, Any]:
    """Responses token counts in the keys every reader of this record already expects.

    Stored converted rather than raw because `Terminal.usage` is read as Anthropic reports it, and a Responses usage read that way is not merely missing the cache fields: its `input_tokens` *includes* what came from cache, so a mostly-cached prompt is reported as having been sent whole. The conversion is the one the buffered path already does, reused rather than repeated — the subtraction is the load-bearing part and two copies of it would drift.

    A malformed usage yields no counts instead of propagating. This runs on the terminal event of a stream whose blocks have already been delivered, and the numbers it produces are for a log line: aborting a delivered response over a field nobody is waiting on would trade a working reply for a cosmetic one.
    """
    try:
        return dict[str, Any](anthropic_usage_from_responses(usage))
    except ResponseConversionError:
        return {}


def _decode_json(raw: str) -> Any:
    try:
        return orjson.loads(raw)
    except orjson.JSONDecodeError:
        # Keep the text rather than dropping it; a malformed argument is still evidence.
        return {"__raw": raw}
