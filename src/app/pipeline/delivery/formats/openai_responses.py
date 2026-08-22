"""Rendering completed blocks as OpenAI Responses SSE frames.

The mirror of `anthropic_messages` beside it, for the other client leg. Same envelope — `event: <type>` then `data: <json>`, verified against `tests/int/cassettes/anthropic_to_responses_stream.json` — and the same promise: every frame describes a block that is already whole.

**This is a reverse translation, and that is the thing to keep in mind when reading it.** `CompletedBlock` is defined as "one fully materialised *Anthropic* content block" (`blocks.py`), so by the time a block reaches here the Responses item it came from has already been mapped into Anthropic's vocabulary by `ResponsesAssembler`. Everything below maps it back. Two consequences are visible in the code and neither is a bug in this module:

- A `web_search_call` item does not survive the round trip. The assembler rewrites it into a text block with prose describing the search, deliberately, because Anthropic has no spelling for it. A Responses client that could have read the real item gets that prose instead. Recorded as a known loss rather than worked around, because undoing it means changing what `CompletedBlock` is.
- A tool call's `arguments` are re-serialised from the parsed object, so whitespace and key order are this proxy's, not upstream's. The `call_id` is upstream's and is forwarded exactly, because the client needs it to answer.

Ids are minted here rather than forwarded, and that is deliberate. Measured on 2026-08-22 across the three cassettes that carry a Responses stream — `anthropic_to_responses_stream`, `history_responses_stream`, `responses_web_search_stream`, out of five in the repository — where every id field in every event differed from every other: 12 of 12, 16 of 16, 125 of 125, including `response.id` itself, which changed between `created`, `in_progress` and `completed`. Upstream's ids identify nothing stable, so passing them through would hand the client an instability it cannot do anything with. What is minted here is consistent within one response, which is what the client's snapshot actually needs.

The sequence is shaped by what the OpenAI SDK's stream parser requires, read from `openai/lib/streaming/responses/_responses.py` at version 3.3.1: `response.created` must arrive first or it raises; `output_index` must equal the current length of the snapshot's output list, because that list is only ever appended to; a text item needs its `content_part.added` before any `output_text` event; and a stream that ends without `response.completed` raises in `get_final_response()`.
`output_index` is therefore counted here and **not** taken from `CompletedBlock.index`, which comes from a counter the assembler also advances for items it later drops — a hole in it would be an IndexError in the client.
"""

import time
from typing import Any, cast

import orjson

from app.pipeline.delivery.assembling import Draft, ReplyDialect, Terminal, decode_json
from app.pipeline.delivery.blocks import TEXT, THINKING, TOOL_USE, CompletedBlock
from app.pipeline.delivery.sse_frame import SseFrame
from app.pipeline.delivery.sse_source import SseEvent
from app.pipeline.server_tool_text import web_search_call_text
from app.pipeline.translation_driver.reasoning_carrier import (
    decode_reasoning_carrier,
    encode_reasoning_carrier,
)
from app.protocols.responses_anthropic import (
    ResponseConversionError,
    anthropic_usage_from_responses,
)

# Stop reasons this proxy synthesises for the Anthropic leg. Responses has no equivalent of either — its vocabulary is completed / incomplete / failed — so both of ours mean the turn finished.
_FINISHED = frozenset({"end_turn", "tool_use", ""})

# Our word for a truncation → the Responses enumeration's word for it. A forward table rather than
# a passthrough with exceptions: `incomplete_details.reason` is an enumeration, so anything not in
# here has no legal spelling and must become null. `max_tokens` is what the assembler writes when
# upstream said `max_output_tokens`; the round trip is deliberate — the record speaks this proxy's
# vocabulary and each leg translates out of it.
_INCOMPLETE_REASONS = {"max_tokens": "max_output_tokens"}


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

    The state is the whole reason this is an object where the Anthropic framer is a thin wrapper over pure functions: a Responses stream carries a sequence number that never repeats, an output index that must not skip, and item ids that have to agree between the event opening an item and the one closing it — none of which a pure function per block could hold.
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
        `response.in_progress` follows immediately because upstream sends it in all three of those recordings and clients use it to mark a request accepted; it costs one frame and the SDK passes it straight through.
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
        """The closing frame group for one whole block. A caller never gets half of one.

        A kind this does not know is refused rather than served as something else — the same choice `block_frames` makes for a compat mode it does not implement, and for the same reason. The `else` used to fall through to `_message`, which reads `payload[TEXT]`; an unknown kind has no such key, so the client was handed an empty assistant turn and "we did not recognise this" became indistinguishable from "upstream sent nothing". It can only fire if a block kind is added without this switch being updated, which is a mistake worth hearing about.
        """
        if block.kind == TOOL_USE:
            frames = self._function_call(block)
        elif block.kind == THINKING:
            frames = self._reasoning(block)
        elif block.kind == TEXT:
            frames = self._message(block)
        else:
            raise ValueError(f"no Responses item shape for block kind {block.kind!r}")
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
                {
                    "output_index": index,
                    "item_id": item_id,
                    "content_index": 0,
                    "delta": text,
                    "logprobs": [],
                },
            ).encode(),
            self._frame(
                "response.output_text.done",
                {
                    "output_index": index,
                    "item_id": item_id,
                    "content_index": 0,
                    "text": text,
                    "logprobs": [],
                },
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

        The frame shape here is the one part of this module not read off a recording: not one of the five cassettes in this repository carries a `function_call` — the three with a Responses stream included — so this follows the SDK's own types and parser instead.
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
                {
                    "output_index": index,
                    "item_id": item_id,
                    "name": opening["name"],
                    "arguments": arguments,
                },
            ).encode(),
            self._frame(
                "response.output_item.done", {"output_index": index, "item": closing}
            ).encode(),
        )

    def _reasoning(self, block: CompletedBlock) -> tuple[bytes, ...]:
        """Reasoning, with no summary delta events.

        Upstream sends none either: in the two of those three that carry a reasoning item at all, it arrives as `added` then `done` with no delta events between them, so this copies that shape rather than inventing a finer-grained one.
        The `summary` list in those recordings is **empty**, so the `summary_text` part written below has the same standing as the `function_call` frames above — it follows the SDK's types, not a recording. Said plainly because the alternative is a reader taking it for measured.

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
        # Passed through as-is: `None` here means nobody observed one, and that is what the wire's own null says.
        usage = terminal.upstream_usage
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
        # Only reasons this protocol has a word for travel. `incomplete_details.reason` is an
        # enumeration, and everything else that can reach here is either our own synthesis
        # (`incomplete`, written by the assembler when upstream gave no reason) or Anthropic's
        # (`stop_sequence`, `pause_turn`, `refusal`) — none of which a Responses client can read.
        # Upstream's own shape for "incomplete, no reason given" is a null, so that is what an
        # unmapped reason becomes rather than a word from the wrong vocabulary.
        reason = _INCOMPLETE_REASONS.get(terminal.stop_reason)
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


# The item type upstream reports a search it ran itself under. Carried as its own draft kind so `_close` can tell it from a message and render it, rather than falling through to the empty-text default.
WEB_SEARCH_CALL = "web_search_call"


class ResponsesAssembler:
    """Assembles blocks from an OpenAI Responses SSE stream.

    An output item is the unit that closes.
    A block therefore completes on `output_item.done`, not on the deltas that preceded it.
    """

    def __init__(self, *, hand_over_stop_reasons: frozenset[str] = frozenset({"max_tokens"})) -> None:
        # Which endings will hand the turn back to the client, and so which ones may drop the block upstream cut short. One setting, because dropping content is only defensible when the client is handed a way to get it back.
        self._hand_over_stop_reasons = hand_over_stop_reasons
        # The block upstream cut short, held rather than emitted or discarded, because at the moment it closes this side does not yet know *why* the response is incomplete — that arrives on the terminal event. Exactly one item can ever be in here: upstream cuts the last one short and then stops.
        self._cut_short: CompletedBlock | None = None
        self._drafts: dict[str, Draft] = {}
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
            # Now the reason is known, the held block can be answered. Kept when this ending will not hand the turn back — the client would otherwise lose a passage it cannot ask for again — and dropped when it will, because the next turn produces it whole.
            held, self._cut_short = self._cut_short, None
            if held is not None and self._terminal.stop_reason not in self._hand_over_stop_reasons:
                self._terminal.record(held)
                return (held,)
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
        self._drafts[key] = Draft(index=self._order, kind=kind, payload=dict(item))
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
            raw = data.get("item")
            item = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
            if str(item.get("type", "")) != WEB_SEARCH_CALL:
                return ()
            # A `web_search_call` that closes without ever having opened. This item is whole on
            # `done` — it has no deltas and nothing to accumulate — so the `added` it skipped
            # carried nothing this needs, and refusing to close it would throw away a search that
            # actually ran, silently. The same regression is on record in the reference project,
            # where the item vanished with no observation of any kind. Registering it late costs
            # nothing; the alternative costs the turn's search.
            draft = Draft(index=self._order, kind=WEB_SEARCH_CALL, payload=dict(item))
            self._order += 1
        # Upstream says on the closing event whether this item is whole: `status: "incomplete"` on the one it cut short, `"completed"` on the rest. Measured 15 times, four of them on a `function_call`, whose `arguments` are then truncated JSON.
        #
        # Held rather than dropped, and only when something whole came before it. Half a sentence is not what the client asked for, but it still beats an empty answer, so the rule reverses when this is all there is — and whether it is dropped at all depends on an ending this side has not been told about yet. Ruled 2026-08-21, narrowed 2026-08-22.
        #
        # A `reasoning` item carries no `status` at all — verified against a completed one, whose key set is identical — so this cannot see a truncated one and does not try. Left open deliberately; `.dev/docs/upstream/retry-and-continuation/deferred.md` §2.
        cut_short = _upstream_cut_this_item_short(data) and self._terminal.blocks > 0
        kind = draft.kind
        if draft.kind == TOOL_USE:
            self._saw_tool_call = True
            payload: dict[str, Any] = {
                "type": TOOL_USE,
                "id": str(draft.payload.get("call_id") or draft.payload.get("id", "")),
                "name": str(draft.payload.get("name", "")),
                "input": decode_json(draft.partial_json or "{}"),
            }
        elif draft.kind == THINKING:
            payload = {
                "type": THINKING,
                THINKING: draft.text,
                "signature": _reasoning_signature(draft, data),
            }
        elif draft.kind == WEB_SEARCH_CALL:
            # Read off the closing event, not the draft. `output_item.added` carries this item with only an id, a status and a type — the query appears for the first time on `done`, and this item has no delta events at all, so the draft has nothing in it to render. Assembling from the draft is what produced an empty text block on every search.
            raw = data.get("item")
            item = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
            payload = {"type": TEXT, TEXT: web_search_call_text(item.get("action"))}
            # Text from here on. The item type is upstream's, and it has no Anthropic spelling to keep.
            kind = TEXT
        else:
            payload = {"type": TEXT, TEXT: draft.text}
        block = CompletedBlock(index=draft.index, kind=kind, payload=payload)
        if cut_short:
            # Not recorded either: a block nobody has received is not a block delivered, and whether anyone ever will is decided on the terminal event.
            self._cut_short = block
            return ()
        self._terminal.record(block)
        return (block,)

    def _read_terminal(self, kind: str, data: dict[str, Any]) -> None:
        self._terminal.seen = True
        raw = data.get("response")
        response = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
        usage = response.get("usage")
        if isinstance(usage, dict):
            self._terminal.usage = _anthropic_usage(cast(dict[str, Any], usage))
            # Kept as it arrived, for the leg that has to report it back in upstream's own shape. See `Terminal.upstream_usage`.
            self._terminal.upstream_usage = dict[str, Any](cast(dict[str, Any], usage))
        if kind == "response.incomplete":
            details = response.get("incomplete_details")
            reason = ""
            if isinstance(details, dict):
                reason = str(cast(dict[str, Any], details).get("reason", ""))
            # `.dev/docs/anthropic-responses-bridge/spec.md`: the output-token limit is max_tokens downstream. That one has an Anthropic spelling; nothing else does, so nothing else is translated.
            #
            # Everything upstream did not name `max_output_tokens` used to become `end_turn`, which reported a turn upstream had cut short as one it finished — the same defect `Terminal.stop_reason` was given an empty default to avoid, reintroduced one field further down. It is upstream's word that goes on the wire now, unmapped. Claude Code's own schema for this field is a nullable string with no enumeration and its readers compare against known values and skip the rest, so a word it does not know costs it nothing; a wrong word it does know costs a reader the truth.
            #
            # `"incomplete"` when upstream said the response was incomplete without saying why. That is still upstream's own word for it — the terminal event is `response.incomplete` and the response carries `status: "incomplete"` — and it keeps the one case with no reason out of `end_turn` as well. Leaving it empty would not: `stream_delivery` fills an empty reason with `end_turn`, which is right for a stream that ended cleanly and says nothing, and wrong here.
            self._terminal.stop_reason = (
                "max_tokens" if reason == "max_output_tokens" else reason or "incomplete"
            )
            return
        self._terminal.stop_reason = TOOL_USE if self._saw_tool_call else "end_turn"


def _upstream_cut_this_item_short(data: dict[str, Any]) -> bool:
    """Whether upstream said, on this closing event, that the item it is closing is not whole.

    `str()` is not used on the way in: an absent field and a null one both mean upstream said nothing, and `str(None)` is the four characters `None`, which is not `"incomplete"` but is also not a value upstream ever sent.
    """
    raw = data.get("item")
    item = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    status = item.get("status")
    return status == "incomplete"


def _reasoning_signature(draft: Draft, closing: dict[str, Any]) -> str:
    """The carrier for a Responses reasoning item, read from the event that closed it.

    `.dev/docs/anthropic-responses-bridge/spec.md` fixes both halves: a non-empty `encrypted_content` must survive value-exact so the
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
