"""Rendering completed blocks as OpenAI Responses SSE frames.

The mirror of `anthropic_sse`, for the other client leg. Same envelope — `event: <type>` then `data: <json>`, verified against `tests/int/cassettes/anthropic_to_responses_stream.json` — and the same promise: every frame describes a block that is already whole.

**This is a reverse translation, and that is the thing to keep in mind when reading it.** `CompletedBlock` is defined as "one fully materialised *Anthropic* content block" (`blocks.py`), so by the time a block reaches here the Responses item it came from has already been mapped into Anthropic's vocabulary by `ResponsesAssembler`. Everything below maps it back. Two consequences are visible in the code and neither is a bug in this module:

- A `web_search_call` item does not survive the round trip. The assembler rewrites it into a text block with prose describing the search, deliberately, because Anthropic has no spelling for it. A Responses client that could have read the real item gets that prose instead. Recorded as a known loss rather than worked around, because undoing it means changing what `CompletedBlock` is.
- A tool call's `arguments` are re-serialised from the parsed object, so whitespace and key order are this proxy's, not upstream's. The `call_id` is upstream's and is forwarded exactly, because the client needs it to answer.

Ids are minted here rather than forwarded, and that is deliberate. Measured across three cassettes on 2026-08-22: every id field in every event differed from every other — 12 of 12, 16 of 16, 125 of 125 — including `response.id` itself, which changed between `created`, `in_progress` and `completed`. Upstream's ids identify nothing stable, so passing them through would hand the client an instability it cannot do anything with. What is minted here is consistent within one response, which is what the client's snapshot actually needs.

The sequence is shaped by what the OpenAI SDK's stream parser requires, read from `openai/lib/streaming/responses/_responses.py` at version 3.3.1: `response.created` must arrive first or it raises; `output_index` must equal the current length of the snapshot's output list, because that list is only ever appended to; a text item needs its `content_part.added` before any `output_text` event; and a stream that ends without `response.completed` raises in `get_final_response()`.
`output_index` is therefore counted here and **not** taken from `CompletedBlock.index`, which comes from a counter the assembler also advances for items it later drops — a hole in it would be an IndexError in the client.
"""

import time
from typing import Any

import orjson

from app.pipeline.delivery.anthropic_sse import SseFrame
from app.pipeline.delivery.assembler import TEXT, THINKING, TOOL_USE, Terminal
from app.pipeline.delivery.blocks import CompletedBlock
from app.pipeline.translation_driver.reasoning_carrier import decode_reasoning_carrier

# Stop reasons this proxy synthesises for the Anthropic leg. Responses has no equivalent of either — its vocabulary is completed / incomplete / failed — so both of ours mean the turn finished.
_FINISHED = frozenset({"end_turn", "tool_use", ""})

# What `stop_reason` says when the assembler saw upstream cut the turn off at the token limit.
_MAX_TOKENS = "max_tokens"


def _json_arguments(value: object) -> str:
    """A tool call's arguments as the string the wire carries.

    The assembler parsed them on the way in, so this re-serialises.
    `{"__raw": …}` is its marker for arguments it could not parse — upstream sent malformed JSON, which is on record for a turn cut short mid-call — and the raw text is handed back rather than the marker, which would otherwise reach the client as a tool argument literally named `__raw`.
    """
    if isinstance(value, dict):
        entries = dict[str, Any](value)  # pyright: ignore[reportUnknownArgumentType]
        raw = entries.get("__raw")
        if len(entries) == 1 and isinstance(raw, str):
            return raw
    return orjson.dumps(value).decode()


class ResponsesFramer:
    """Writes one response's frames. Stateful, and one per request.

    The state is the whole reason this is an object where `anthropic_sse` is a set of functions: a Responses stream carries a sequence number that never repeats, an output index that must not skip, and item ids that have to agree between the event opening an item and the one closing it — none of which a pure function per block could hold.
    """

    def __init__(self, *, response_id: str, model: str, created_at: float | None = None) -> None:
        self._response_id = response_id
        self._model = model
        self._created_at = int(created_at if created_at is not None else time.time())
        self._sequence = 0
        self._output_index = 0
        self._items: list[dict[str, Any]] = []

    def _frame(self, event_type: str, body: dict[str, Any]) -> SseFrame:
        """One event, stamped with the next sequence number.

        Every frame goes through here so the counter cannot be advanced in one place and read in another.
        `sequence_number` has no default in any of the SDK's event models, so it is sent on all of them rather than only where a reader is known to look.
        """
        payload: dict[str, Any] = {"type": event_type, "sequence_number": self._sequence}
        payload.update(body)
        self._sequence += 1
        return SseFrame(event_type, payload)

    def _item_id(self, prefix: str) -> str:
        return f"{prefix}_{self._response_id}_{self._output_index}"

    def _response_object(
        self,
        *,
        status: str,
        completed_at: int | None = None,
        usage: dict[str, Any] | None = None,
        incomplete_reason: str | None = None,
    ) -> dict[str, Any]:
        """The `response` object every envelope event carries.

        Only the fields the SDK's model declares without a default are guaranteed here — `id`, `created_at`, `object`, `output`, `parallel_tool_calls`, `tool_choice`, `tools`, `model` — plus the ones a reader acts on.
        Upstream sends a few dozen more, including its own billing extensions; those are not copied, because this proxy has no value for them and echoing a shape it did not compute would be inventing one.
        """
        return {
            "id": self._response_id,
            "object": "response",
            "created_at": self._created_at,
            "completed_at": completed_at,
            "status": status,
            "model": self._model,
            "output": list(self._items),
            "usage": usage,
            "error": None,
            "incomplete_details": (
                {"reason": incomplete_reason} if incomplete_reason is not None else None
            ),
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "metadata": {},
        }

    def preamble(self) -> tuple[bytes, ...]:
        """Open the response.

        Sent with the first block rather than on its own, the same way `message_start` is, so a turn that never produces one never looks to the client like a turn that began.
        `response.in_progress` follows immediately because upstream sends it in all three recordings and clients use it to mark a request accepted; it costs one frame and the SDK passes it straight through.
        """
        return (
            self._frame(
                "response.created", {"response": self._response_object(status="in_progress")}
            ).encode(),
            self._frame(
                "response.in_progress", {"response": self._response_object(status="in_progress")}
            ).encode(),
        )

    def block(self, block: CompletedBlock) -> tuple[bytes, ...]:
        """The closing frame group for one whole block. A caller never gets half of one."""
        if block.kind == TOOL_USE:
            frames = self._function_call(block)
        elif block.kind == THINKING:
            frames = self._reasoning(block)
        else:
            frames = self._message(block)
        self._output_index += 1
        return frames

    def _message(self, block: CompletedBlock) -> tuple[bytes, ...]:
        text = str(block.payload.get(TEXT, ""))
        index = self._output_index
        item_id = self._item_id("msg")
        part: dict[str, Any] = {
            "type": "output_text",
            "text": text,
            "annotations": [],
            "logprobs": [],
        }
        opening: dict[str, Any] = {
            "id": item_id,
            "type": "message",
            "role": "assistant",
            "status": "in_progress",
            "content": [],
        }
        closing: dict[str, Any] = {**opening, "status": "completed", "content": [part]}
        self._items.append(closing)
        return (
            self._frame(
                "response.output_item.added", {"output_index": index, "item": opening}
            ).encode(),
            self._frame(
                "response.content_part.added",
                {
                    "output_index": index,
                    "item_id": item_id,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": "", "annotations": [], "logprobs": []},
                },
            ).encode(),
            # One delta carrying the finished text. The block is already whole, so this is not a piece of it — it is here because a client that renders only deltas would otherwise see nothing at all. The same reasoning as `_delta_for` on the Anthropic leg.
            self._frame(
                "response.output_text.delta",
                {"output_index": index, "item_id": item_id, "content_index": 0, "delta": text},
            ).encode(),
            self._frame(
                "response.output_text.done",
                {"output_index": index, "item_id": item_id, "content_index": 0, "text": text},
            ).encode(),
            self._frame(
                "response.content_part.done",
                {"output_index": index, "item_id": item_id, "content_index": 0, "part": part},
            ).encode(),
            self._frame(
                "response.output_item.done", {"output_index": index, "item": closing}
            ).encode(),
        )

    def _function_call(self, block: CompletedBlock) -> tuple[bytes, ...]:
        """A tool call.

        The frame shape here is the one part of this module not read off a recording: none of the three cassettes in this repository carries a `function_call`, so this follows the SDK's own types and parser instead.
        `arguments` starts empty and arrives in a single delta because the parser accumulates it with `+=` — giving it in full on the opening item *and* in a delta would double it.
        """
        index = self._output_index
        item_id = self._item_id("fc")
        arguments = _json_arguments(block.payload.get("input", {}))
        opening: dict[str, Any] = {
            "id": item_id,
            "type": "function_call",
            "call_id": str(block.payload.get("id", "")),
            "name": str(block.payload.get("name", "")),
            "arguments": "",
            "status": "in_progress",
        }
        closing: dict[str, Any] = {**opening, "arguments": arguments, "status": "completed"}
        self._items.append(closing)
        return (
            self._frame(
                "response.output_item.added", {"output_index": index, "item": opening}
            ).encode(),
            self._frame(
                "response.function_call_arguments.delta",
                {"output_index": index, "item_id": item_id, "delta": arguments},
            ).encode(),
            self._frame(
                "response.function_call_arguments.done",
                {"output_index": index, "item_id": item_id, "arguments": arguments},
            ).encode(),
            self._frame(
                "response.output_item.done", {"output_index": index, "item": closing}
            ).encode(),
        )

    def _reasoning(self, block: CompletedBlock) -> tuple[bytes, ...]:
        """Reasoning, with no summary delta events.

        Upstream sends none either — in all three recordings a reasoning item arrives as `added` then `done` with the summary already in place — so this copies that shape rather than inventing a finer-grained one.

        `encrypted_content` is written only when there was some. The assembler stores this project's own carrier in the block's `signature`, and an empty carrier is still a non-empty marker string, so decoding is what tells "upstream sealed some reasoning" apart from "upstream sent none". Emitting the marker itself would hand the client a token it cannot use.
        """
        index = self._output_index
        item_id = self._item_id("rs")
        summary_text = str(block.payload.get(THINKING, ""))
        item: dict[str, Any] = {
            "id": item_id,
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": summary_text}] if summary_text else [],
            "content": [],
        }
        carrier = decode_reasoning_carrier(str(block.payload.get("signature", "")))
        if carrier.encrypted_content:
            item["encrypted_content"] = carrier.encrypted_content
        self._items.append(item)
        return (
            self._frame(
                "response.output_item.added", {"output_index": index, "item": item}
            ).encode(),
            self._frame("response.output_item.done", {"output_index": index, "item": item}).encode(),
        )

    def terminal(self, terminal: Terminal) -> tuple[bytes, ...]:
        """Close the response. Only valid once every block has been framed.

        `usage` is upstream's own, carried through untouched, and absent rather than zeroed when it was never seen.
        The `Terminal.usage` beside it has been through the Anthropic conversion — which subtracts the cached part of the input and discards `reasoning_tokens` — so converting it back would compose two lossy passes and report a number no side ever computed.
        """
        usage = terminal.upstream_usage or None
        if terminal.stop_reason in _FINISHED:
            return (
                self._frame(
                    "response.completed",
                    {
                        "response": self._response_object(
                            status="completed", completed_at=int(time.time()), usage=usage
                        )
                    },
                ).encode(),
            )
        reason = (
            "max_output_tokens" if terminal.stop_reason == _MAX_TOKENS else terminal.stop_reason
        )
        return (
            self._frame(
                "response.incomplete",
                {
                    "response": self._response_object(
                        status="incomplete",
                        completed_at=int(time.time()),
                        usage=usage,
                        incomplete_reason=reason,
                    )
                },
            ).encode(),
        )

    def error(self, *, error_type: str, message: str, code: str | None = None) -> bytes:
        """The one frame that says a started stream will not end successfully.

        `error`, not `response.failed`. The latter has to carry a whole `Response` object, and at the point this is sent that object is half-built — no usage, output cut off mid-turn — so filling one in would be stating things that are not so. The SDK passes `error` through without asserting anything about it.

        Responses' error event has `code`, `message` and `param` and no field for a category, while the Anthropic leg's has `type`. The category is prefixed onto the message rather than overwriting `code`, because `code` is the stable machine-readable half and callers already match on values like `incomplete_responses_stream`.

        Mutually exclusive with `terminal`, the same as on the Anthropic leg. Nothing here enforces that; the caller picks one.
        """
        return self._frame(
            "error",
            {
                "code": code,
                "message": f"{error_type}: {message}" if error_type else message,
                "param": None,
            },
        ).encode()

    def keepalive(self) -> bytes:
        """The same SSE comment the Anthropic leg uses.

        A comment carries no event name, so no parser on either side turns it into an event and it cannot be mistaken for part of the turn.
        Deliberately not `response.in_progress`: the SDK hands that one to the application, and repeating it through a long wait would turn "your request was accepted" into noise and make the sequence numbers say something they do not mean.
        """
        return b": ping\n\n"
