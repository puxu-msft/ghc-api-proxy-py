"""Assembling upstream SSE events into complete blocks.

A block is emitted when its closing event arrives, never on a delta.
The assembler is what makes "complete block" a fact rather than a hope.

Two upstream shapes are handled, matching the two protocol legs.
Both produce the same `CompletedBlock`, so delivery never learns which upstream a block is from.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, cast

import orjson

from app.pipeline.delivery.blocks import CompletedBlock
from app.pipeline.delivery.sse_source import SseEvent

TEXT = "text"
THINKING = "thinking"
TOOL_USE = "tool_use"


@dataclass(slots=True)
class Terminal:
    """What the upstream said when it finished."""

    stop_reason: str = "end_turn"
    usage: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    seen: bool = False


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
        return (CompletedBlock(index=draft.index, kind=draft.kind, payload=payload),)

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
        self._terminal = Terminal()
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
            payload = {"type": THINKING, THINKING: draft.text, "signature": ""}
        else:
            payload = {"type": TEXT, TEXT: draft.text}
        return (CompletedBlock(index=draft.index, kind=draft.kind, payload=payload),)

    def _read_terminal(self, kind: str, data: dict[str, Any]) -> None:
        self._terminal.seen = True
        raw = data.get("response")
        response = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
        usage = response.get("usage")
        if isinstance(usage, dict):
            self._terminal.usage = dict[str, Any](cast(dict[str, Any], usage))
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


def _decode_json(raw: str) -> Any:
    try:
        return orjson.loads(raw)
    except orjson.JSONDecodeError:
        # Keep the text rather than dropping it; a malformed argument is still evidence.
        return {"__raw": raw}
