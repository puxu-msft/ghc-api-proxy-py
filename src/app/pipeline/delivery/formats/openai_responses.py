"""Rendering completed blocks as OpenAI Responses SSE frames.

The mirror of `anthropic_messages` beside it, for the other client leg. Same envelope — `event: <type>` then `data: <json>`, verified against `tests/int/cassettes/anthropic_to_responses_stream.json` — and the same promise: every frame describes a block that is already whole.

**This is a reverse translation, and that is the thing to keep in mind when reading it.** `CompletedBlock` is defined as "one fully materialised *Anthropic* content block" (`blocks.py`), so by the time a block reaches here the Responses item it came from has already been mapped into Anthropic's vocabulary by `ResponsesAssembler`. Everything below maps it back. Two consequences are visible in the code and neither is a bug in this module:

- A `web_search_call` item does not survive the round trip. The assembler rewrites it into a text block with prose describing the search, and a Responses client that could have read the real item gets that prose instead. **This is an unimplemented requirement, not a property of the formats.** The reason recorded here until 2026-08-30 — "deliberately, because Anthropic has no spelling for it ... recorded as a known loss rather than worked around" — was false twice over: Anthropic spells it `server_tool_use` paired with `web_search_tool_result` (`hosted-web-search-spec.md` §5.3, ruled by the user as D6 on 2026-08-20), and calling it a known loss is what kept it from being worked around. Restoring the pair needs the `url_citation` annotations that arrive on the following text item, which nothing reads yet; §6.3 also moves where the block closes.
- A tool call's `arguments` are re-serialised from the parsed object, so whitespace and key order are this proxy's, not upstream's. The `call_id` is upstream's and is forwarded exactly, because the client needs it to answer.

Ids are minted here rather than forwarded, and that is deliberate. Measured on 2026-08-22 across the three cassettes that carry a Responses stream — `anthropic_to_responses_stream`, `history_responses_stream`, `responses_web_search_stream`, out of five in the repository — where every id field in every event differed from every other: 12 of 12, 16 of 16, 125 of 125, including `response.id` itself, which changed between `created`, `in_progress` and `completed`. Upstream's ids identify nothing stable, so passing them through would hand the client an instability it cannot do anything with. What is minted here is consistent within one response, which is what the client's snapshot actually needs.

The sequence is shaped by what the OpenAI SDK's stream parser requires, read from `openai/lib/streaming/responses/_responses.py` at version 3.3.1: `response.created` must arrive first or it raises; `output_index` must equal the current length of the snapshot's output list, because that list is only ever appended to; a text item needs its `content_part.added` before any `output_text` event; and a stream that ends without `response.completed` raises in `get_final_response()`.
`output_index` is therefore counted here and **not** taken from `CompletedBlock.index`, which comes from a counter the assembler also advances for items it later drops — a hole in it would be an IndexError in the client.
"""

import logging
import time
from typing import Any, cast

import orjson

from app.errors import OPENAI_ERROR_TYPES, STATUS_FOR_CATEGORY, ErrorCategory, ErrorInfo
from app.pipeline.delivery.assembling import (
    Draft,
    FailureOrigin,
    ReasoningSummaryDraft,
    ReplyDialect,
    StreamFailure,
    Terminal,
    decode_json,
)
from app.pipeline.delivery.blocks import (
    REDACTED_THINKING,
    TEXT,
    THINKING,
    TOOL_USE,
    CompletedBlock,
)
from app.pipeline.delivery.sse_frame import SseFrame
from app.pipeline.delivery.sse_source import SseEvent
from app.pipeline.server_tool_text import web_search_call_text
from app.pipeline.translation_driver.reasoning_bridge import (
    ReasoningBridgeError,
    read_anthropic_reasoning,
    read_responses_reasoning,
    reasoning_to_anthropic,
    reasoning_to_responses,
)

# The buffered half of this same client leg owns these two tables; this is the streaming half. They were duplicated until 2026-08-27 and kept in step by a comment on each — `fef7d96` is the record of what it costs when the two halves describe one ending differently, so "the same set" is worth making checkable rather than remembered. The import runs `delivery` → `translation_driver`, which is the direction this module already depends in.
from app.pipeline.translation_driver.responses import (
    FINISHED_STOP_REASONS,
    INCOMPLETE_REASONS,
)
from app.protocols.responses_anthropic import (
    ResponseConversionError,
    anthropic_usage_from_responses,
)

logger = logging.getLogger(__name__)

# The three ways this upstream says a stream failed, and the two places it puts the words.
# The vocabulary is the official client's own table (`chatWebSocketManager.ts`), minus its two successful terminals. `response.failed` and `response.cancelled` carry a whole response object with the words nested under `response.error`; `error` is the one that differs by upstream, and both spellings are read — see `_failure_words`.
# **Not from a recording**: all five cassettes in this repository contain zero of these events, so the shapes are second-hand and the extraction is written to survive being wrong about them (missing keys read as empty, never raise). `response.cancelled` in particular is recorded in `.dev/docs/upstream/retry-and-continuation/deferred.md` 第 4 条 and `reports/260821-upstream-termination-reasons.md`.
# This leg's own name, as `WireFormat` spells it.
OPENAI_RESPONSES = "openai-responses"

_FAILURE_EVENTS = frozenset({"error", "response.failed", "response.cancelled"})


def _words(holder: dict[str, Any]) -> tuple[str, str]:
    """`code` and `message` out of whichever object carries them.

    `code` is `str | None` in the SDK's own model, so a null is a normal value here rather than a malformed one; it must read as absent and not as the string `None`.
    """
    code = holder.get("code")
    message = holder.get("message")
    return (str(code) if code is not None else ""), (str(message) if message is not None else "")


def _failure_words(kind: str, data: dict[str, Any]) -> tuple[str, str]:
    """Upstream's own code and message for a failure event, or empty strings if it did not say.

    Two shapes for `error`, and this upstream uses the second. OpenAI's public SDK declares `ResponseErrorEvent` flat — `{type, code, message}` — but CAPI wraps them: `{type: "error", error: {code, message}}`, which `chatWebSocketManager.ts` documents by name precisely because the two differ. Reading only the flat one printed `code='' message=''` on the shape we are most likely to meet, which is the whole of what this log line exists to carry. The nested object is preferred and the flat one is the fallback; nothing sends both, so no precedence question arises.
    """
    if kind == "error":
        nested = data.get("error")
        if isinstance(nested, dict):
            return _words(cast(dict[str, Any], nested))
        return _words(data)
    raw = data.get("response")
    response = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    nested = response.get("error")
    return _words(cast(dict[str, Any], nested) if isinstance(nested, dict) else {})


def responses_failure_from(event: SseEvent) -> StreamFailure | None:
    """Upstream's own failure event as a failure record, or `None` when this event is not one.

    Module-level and shared, because **both legs of this dialect ask the same question**: the translating assembler asks it to stop pretending the turn succeeded, and the direct leg's passthrough asks it to replay upstream's own words. A second copy would be a second answer, and the first thing to drift would be the nested-versus-flat `error` shape that `_failure_words` exists to get right.

    The log line lives here for the reason ruled 2026-08-22: a path we knowingly do not handle must still be logged, and it is still the only record an operator reads. `warning` rather than something quieter because the zero behind it is a **discriminating** zero — the same sweep over 134336 operations counted 64351 `response.completed`, so the measurement could see this class of event and found none. One arriving despite that is worth attention.
    """
    data = event.json()
    kind = event.event or str(data.get("type", ""))
    if kind not in _FAILURE_EVENTS:
        return None
    code, message = _failure_words(kind, data)
    logger.warning("upstream sent %r mid-stream: code=%r message=%r", kind, code, message)
    return StreamFailure(
        origin=FailureOrigin.UPSTREAM_EVENT,
        # Upstream's own event name, kept rather than normalised to `error`. `response.failed` and `response.cancelled` are different things to a client of that API, and a direct leg replays whichever arrived.
        event=kind,
        raw_data=event.data,
        info=ErrorInfo(
            category=ErrorCategory.UPSTREAM,
            message=message or f"upstream sent {kind}",
            status_code=STATUS_FOR_CATEGORY[ErrorCategory.UPSTREAM],
            code=code or kind,
            source_format=OPENAI_RESPONSES,
            source_bytes=event.data.encode(),
        ),
    )


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
        elif block.kind in {THINKING, REDACTED_THINKING}:
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
        """One whole Anthropic reasoning block projected into a client-facing Responses item."""
        index = self._output_index
        item_id = self._item_id("rs")
        content = block.reasoning or read_anthropic_reasoning(block.payload)
        projected = reasoning_to_responses(content, bridge_for_client=True)
        item: dict[str, Any] = {"id": item_id, **projected, "content": []}
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
        if terminal.stop_reason in FINISHED_STOP_REASONS:
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
        # Only reasons this protocol has a word for travel. `incomplete_details.reason` is an enumeration, and everything else that can reach here is either our own synthesis (`incomplete`, written by the assembler when upstream gave no reason) or Anthropic's (`stop_sequence`, `pause_turn`, `refusal`) — none of which a Responses client can read.
        # Upstream's own shape for "incomplete, no reason given" is a null, so that is what an unmapped reason becomes rather than a word from the wrong vocabulary.
        reason = INCOMPLETE_REASONS.get(terminal.stop_reason)
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

    def error(self, info: ErrorInfo) -> bytes:
        """The one frame that says a started stream will not end successfully.

        `error`, not `response.failed`. The latter has to carry a whole `Response` object, and at the point this is sent that object is half-built — no usage, output cut off mid-turn — so filling one in would be stating things that are not so. The SDK passes `error` through without asserting anything about it.

        **Flat, and deliberately not the shape the Anthropic leg uses.** `ResponseErrorEvent` declares `code`, `message` and `param`, with the event's own `type` fixed to the literal `"error"` and no field for a category. So the category is prefixed onto the message — `code` is the stable machine-readable half and callers already match on values like `incomplete_responses_stream`, so overwriting it would cost more than it buys. `.dev/docs/error-envelope/spec.md` §6.3 is where the two shapes are set out side by side; they are not two spellings of one envelope.

        Mutually exclusive with `terminal`, the same as on the Anthropic leg. Nothing here enforces that; the caller picks one.
        """
        spelled = OPENAI_ERROR_TYPES[info.category]
        return self._frame(
            "error",
            {
                "code": info.code or None,
                "message": f"{spelled}: {info.message}" if spelled else info.message,
                "param": info.param or None,
            },
        ).encode()

    @property
    def synthesises_terminal(self) -> bool:
        """Yes: this framer writes every frame the client sees, so it can honestly write the last one."""
        return True

    def keepalive(self) -> bytes:
        """The same SSE comment the Anthropic leg uses.

        A comment carries no event name, so no parser on either side turns it into an event and it cannot be mistaken for part of the turn.
        Deliberately not `response.in_progress`: the SDK hands that one to the application, and repeating it through a long wait would turn "your request was accepted" into noise and make the sequence numbers say something they do not mean.
        """
        return b": ping\n\n"


# The item type upstream reports a search it ran itself under. Carried as its own draft kind so `_close` can tell it from a message and render it, rather than falling through to the empty-text default.
WEB_SEARCH_CALL = "web_search_call"
TOOL_SEARCH_CALL = "tool_search_call"
TOOL_SEARCH_OUTPUT = "tool_search_output"
# A draft kind meaning "recognised, and deliberately not delivered". Distinct from an unrecognised item, which is `UNKNOWN` below.
DISCARDED = "discarded"
# A draft kind meaning **"this proxy does not know what this item is"**, which is a different fact from `DISCARDED` and gets the opposite treatment.
#
# It exists because the fallback used to be the item's own type string. That produced a `CompletedBlock` whose `kind` was, say, `custom_tool_call` while its payload was `{"type": "text", "text": ""}` — a block contradicting itself, and empty besides, because an unrecognised item's content arrives on events this assembler does not consume (`response.custom_tool_call_input.delta` for that one). The two legs then failed differently and neither was right: `ResponsesFramer` raised `ValueError` mid-stream after a 200 (**GitHub issue #2**), and `AnthropicFramer` sent a `content_block_start` with empty text — a shape upstream refuses when the turn is replayed, delivered under a `stop_reason` of `end_turn` that told the client the model had finished while it was in fact waiting on a tool call.
#
# `anthropic-responses-bridge/spec.md`'s response matrix has required the answer all along, and its wording names both of those failures: 未知 output item → `REJECT`, **不得由空 text block或正常 terminal 掩盖**. So this is not new behaviour; it is the implementation arriving at a clause that was already frozen. The same document requires the streaming and non-streaming paths to be equivalent, which is why `translation_driver/responses.py` changes with it.
UNKNOWN = "unknown"


class ResponsesAssembler:
    """Assembles blocks from an OpenAI Responses SSE stream.

    An output item is the unit that closes.
    A block therefore completes on `output_item.done`, not on the deltas that preceded it.
    """

    def __init__(
        self,
        *,
        hand_over_stop_reasons: frozenset[str] = frozenset({"max_tokens"}),
        client_search_tool: str = "",
    ) -> None:
        # The name a `tool_search_call` is delivered under. It cannot be read from the stream — on this wire the search *is* the tool, so the item names nothing — and without it such an item would fall through to the unknown branch and reach the client as an empty text block. Empty here means this request translated no tool search, in which case no such item is expected.
        self._client_search_tool = client_search_tool
        # Which endings will hand the turn back to the client, and so which ones may drop the block upstream cut short. One setting, because dropping content is only defensible when the client is handed a way to get it back.
        self._hand_over_stop_reasons = hand_over_stop_reasons
        # The block upstream cut short, held rather than emitted or discarded, because at the moment it closes this side does not yet know *why* the response is incomplete — that arrives on the terminal event. Exactly one item can ever be in here: upstream cuts the last one short and then stops.
        self._cut_short: CompletedBlock | None = None
        self._drafts: dict[str, Draft] = {}
        # **Block numbers are handed out when a deliverable block is formed, not when its item opens.** A block held as `_cut_short` reserves its number before anyone receives it; that is safe because such an item is the last one — the field above says so — so a number reserved and then dropped has no later block to leave a hole in front of, and the hand-back block that may follow numbers itself from `DeliverySession.committed_count`. The Anthropic framer writes this number into `content_block_start`, `_delta`, `_stop` and `signature_delta` verbatim, so a number that is allocated and then never used is a hole in the client's sequence, and two blocks sharing one is a second block read as a continuation of the first.
        #
        # It used to count items. That is the same thing only while every item yields exactly one block, and it already did not: `_open` advances unconditionally, while a `DISCARDED` item — `tool_search_output` always, `tool_search_call` whenever no client tool name is known — emits nothing. Measured 2026-08-30 on this file's own `HEAD`: a discarded item followed by a message delivered one block, numbered **1**, with no block 0 ever sent.
        #
        # The module docstring notes that `ResponsesFramer` counts its own `output_index` rather than reading this field, and gives that same counter as the reason. That is this leg protecting itself; it did nothing for the Anthropic leg, which reads the field.
        self._emitted = 0
        self._terminal = Terminal(dialect=ReplyDialect.RESPONSES)
        self._saw_tool_call = False
        self._failure: StreamFailure | None = None

    @property
    def failure(self) -> StreamFailure | None:
        return self._failure

    @property
    def terminal(self) -> Terminal:
        return self._terminal

    def close(self) -> tuple[CompletedBlock, ...]:
        """Nothing: what this assembler still holds is a half-built block, which every ending drops."""
        return ()

    @property
    def queued_bytes(self) -> int:
        """Zero, and see `BlockAssembler.queued_bytes` for why that is the pre-existing accounting."""
        return 0

    @property
    def cut_mid_block(self) -> bool:
        """A draft still open, **or one upstream already told us it cut short**. See `BlockAssembler`.

        The second half is what this leg needs and the other does not. `_close` pops the draft the moment `output_item.done` arrives and, when upstream marked that item `status: "incomplete"`, parks the block in `_cut_short` instead of releasing it — so `_drafts` is empty while a block sits cut short and undelivered. Reading only `_drafts` there answered "stopped at a block boundary" for a stream upstream had explicitly said was severed, and the clean close that followed dropped that block in silence where the old ending had at least been loud. Measured 2026-08-22.

        Anthropic has no equivalent state: a `content_block_stop` closes and delivers in one step, so `_drafts` and "was anything cut" are the same question there.
        """
        return bool(self._drafts) or self._cut_short is not None

    def push(self, event: SseEvent) -> tuple[CompletedBlock, ...]:
        data = event.json()
        kind = event.event or str(data.get("type", ""))

        if kind == "response.output_item.added":
            self._open(data)
            return ()
        if kind == "response.output_text.delta":
            self._accumulate(data, str(data.get("delta", "")))
            return ()
        if kind == "response.reasoning_summary_part.added":
            self._open_summary_part(data)
            return ()
        if kind == "response.reasoning_summary_text.delta":
            self._accumulate_summary_text(data, str(data.get("delta", "")))
            return ()
        if kind == "response.reasoning_summary_text.done":
            self._finish_summary_text(data)
            return ()
        if kind == "response.reasoning_summary_part.done":
            self._finish_summary_part(data)
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
        if kind in _FAILURE_EVENTS:
            # Upstream said this turn failed, and since 2026-08-24 that is carried rather than logged and dropped.
            #
            # **The comment this replaces was already wrong.** It said the client received the same `incomplete_responses_stream` frame a tear produces, "and the two remain indistinguishable on the wire". After the clean-EOF change of 2026-08-22 that path stopped producing an error frame at all: the client got `response.incomplete` with `error: null` — a terminal event that reads as an orderly ending. An upstream failure was indistinguishable from success, not from a tear. `.dev/docs/error-envelope/spec.md` §3.5.
            self._failure = responses_failure_from(event)
            return ()
        return ()

    def _item_key(self, data: dict[str, Any]) -> str:
        """Which draft an event belongs to.

        `output_index` first, because it is the only identifier this upstream keeps stable: Copilot sends a *different* `item.id` on `output_item.added` and `output_item.done` for the same item, so keying on the id meant `_close` never found what `_open` had created and the whole response assembled into nothing. The ids are kept as a fallback for upstreams that omit the index; between the two, only the index is load-bearing.
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
            # Delivered as a call on the client's own tool when a name is known. **Without one it is discarded rather than left to fall through**: the fallback renders an empty text block, and an assistant turn carrying one is refused when the client replays it. Discarding loses the model's search request either way; the difference is whether the turn stays replayable.
            TOOL_SEARCH_CALL: TOOL_USE if self._client_search_tool else DISCARDED,
            # The upstream's own account of a **hosted** search: it ran the search and is reporting what it loaded. There is no Anthropic block for that, and the client did not ask for one — it asked for a hosted search, whose whole point is that it happens elsewhere.
            # Listed explicitly, and it was not until the fallback stopped being "the item's own type". `_close` dispatches on `draft.kind == WEB_SEARCH_CALL`, and that branch only ever ran because `.get(item_type, item_type)` happened to hand back the right string — an implicit dependency on the very fallback that produced issue #2. Naming it here is what keeps the two facts separate: this item **is** recognised, it just has no entry in the map above because its kind is its own name.
            WEB_SEARCH_CALL: WEB_SEARCH_CALL,
            TOOL_SEARCH_OUTPUT: DISCARDED,
        }.get(item_type, UNKNOWN)
        key = self._item_key(data)
        # `-1` because on this leg a draft does not own a block number; `_close` takes one from `_emitted` when it actually emits. Deliberately not `0`, which would be a plausible-looking wrong answer if anything ever read it again.
        self._drafts[key] = Draft(index=-1, kind=kind, payload=dict(item))

    def _accumulate(self, data: dict[str, Any], delta: str) -> None:
        draft = self._drafts.get(self._item_key(data))
        if draft is not None:
            draft.text += delta

    def _open_summary_part(self, data: dict[str, Any]) -> None:
        draft = self._reasoning_draft(data)
        index = self._summary_index(data)
        if index in draft.reasoning_summary:
            raise ReasoningBridgeError(
                "reasoning_summary_lifecycle",
                f"summary part {index} opened more than once",
            )
        raw = data.get("part")
        part = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
        if part.get("type") != "summary_text" or not isinstance(part.get("text"), str):
            raise ReasoningBridgeError(
                "reasoning_summary_unsupported_part",
                f"summary part {index} must be summary_text with string text",
            )
        extensions = {
            key: value for key, value in part.items() if key not in {"type", "text"}
        }
        draft.reasoning_summary[index] = ReasoningSummaryDraft(
            text=cast(str, part["text"]),
            extensions=extensions,
        )

    def _accumulate_summary_text(self, data: dict[str, Any], delta: str) -> None:
        index, part = self._summary_part(data)
        if part.text_done or part.part_done:
            raise ReasoningBridgeError(
                "reasoning_summary_lifecycle",
                f"summary part {index} received a delta after done",
            )
        part.text += delta

    def _finish_summary_text(self, data: dict[str, Any]) -> None:
        index, part = self._summary_part(data)
        text = data.get("text")
        if not isinstance(text, str):
            raise ReasoningBridgeError(
                "reasoning_summary_malformed",
                f"summary text done {index} has no string text",
            )
        if part.text_done or part.part_done:
            raise ReasoningBridgeError(
                "reasoning_summary_lifecycle",
                f"summary text {index} completed more than once",
            )
        part.text = text
        part.text_done = True

    def _finish_summary_part(self, data: dict[str, Any]) -> None:
        index, part = self._summary_part(data)
        if part.part_done:
            raise ReasoningBridgeError(
                "reasoning_summary_lifecycle",
                f"summary part {index} completed more than once",
            )
        status = data.get("status")
        if status == "incomplete":
            part.incomplete = True
            part.part_done = True
            return
        if status is not None:
            raise ReasoningBridgeError(
                "reasoning_summary_malformed",
                f"summary part {index} has unsupported status {status!r}",
            )
        raw = data.get("part")
        closed = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
        if closed.get("type") != "summary_text" or not isinstance(closed.get("text"), str):
            raise ReasoningBridgeError(
                "reasoning_summary_unsupported_part",
                f"summary part {index} must close with summary_text and string text",
            )
        part.text = cast(str, closed["text"])
        part.extensions = {
            key: value for key, value in closed.items() if key not in {"type", "text"}
        }
        part.part_done = True

    def _reasoning_draft(self, data: dict[str, Any]) -> Draft:
        draft = self._drafts.get(self._item_key(data))
        if draft is None or draft.kind != THINKING:
            raise ReasoningBridgeError(
                "reasoning_summary_lifecycle",
                "reasoning summary event has no open reasoning item",
            )
        return draft

    def _summary_part(
        self, data: dict[str, Any]
    ) -> tuple[int, ReasoningSummaryDraft]:
        draft = self._reasoning_draft(data)
        index = self._summary_index(data)
        part = draft.reasoning_summary.get(index)
        if part is None:
            raise ReasoningBridgeError(
                "reasoning_summary_lifecycle",
                f"summary part {index} was not opened",
            )
        return index, part

    @staticmethod
    def _summary_index(data: dict[str, Any]) -> int:
        index = data.get("summary_index")
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise ReasoningBridgeError(
                "reasoning_summary_malformed",
                "reasoning summary event requires a non-negative summary_index",
            )
        return index

    @staticmethod
    def _summary_from_draft(draft: Draft) -> list[dict[str, Any]]:
        if any(part.incomplete for part in draft.reasoning_summary.values()):
            raise ReasoningBridgeError(
                "incomplete_reasoning_summary",
                "reasoning summary ended incomplete without a closing summary",
            )
        indexes = sorted(draft.reasoning_summary)
        if indexes != list(range(len(indexes))):
            raise ReasoningBridgeError(
                "reasoning_summary_lifecycle",
                "reasoning summary indices must be continuous from zero",
            )
        return [
            {
                "type": "summary_text",
                "text": draft.reasoning_summary[index].text,
                **dict(draft.reasoning_summary[index].extensions),
            }
            for index in indexes
        ]

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
            late = str(item.get("type", ""))
            # `tool_search_call` joins `web_search_call` here because the two are structurally the same on this wire: whole on `done`, no deltas, nothing for `added` to have carried. Only when a name is known to deliver it under — without one there is nothing to build.
            rescuable = late == WEB_SEARCH_CALL or (
                late == TOOL_SEARCH_CALL and bool(self._client_search_tool)
            )
            if not rescuable:
                # The one discard on this leg that has already cost a whole response, and it was silent while it did it: Copilot sends a different `item.id` on `added` and `done`, so keying drafts on that id meant no close ever found what its open had created, and the reply assembled into zero bytes with 1243 tests green. `_item_key` prefers `output_index` now and that particular cause is gone, but "a close with no draft" still means an output item disappears, and it disappears because an invariant this side holds was broken by an upstream this side cannot see into.
                # `warning` and not something quieter, for the same reason the failure events above are: this is not a skip anyone planned, and every occurrence is content the client asked for and did not get. Reported rather than raised, because the rest of the turn is still deliverable and refusing it would cost more than the item.
                # The open keys are the "why" half — they are what the lookup was compared against, so a key reading `index:7` beside drafts holding `index:0` says which of the two identifiers moved. The item's payload is deliberately not logged; its type and its id are what identify it.
                logger.warning(
                    "dropping an output item that closed without ever opening: type=%r item_id=%r key=%r open_drafts=%r",
                    late,
                    str(item.get("id", "")),
                    key,
                    sorted(self._drafts),
                )
                return ()
            # An item that closes without ever having opened. This item is whole on `done` — it has no deltas and nothing to accumulate — so the `added` it skipped carried nothing this needs, and refusing to close it would throw away a search that actually ran, silently. The same regression is on record in the reference project, where the item vanished with no observation of any kind. Registering it late costs nothing; the alternative costs the turn's search.
            draft = Draft(
                index=-1,
                kind=TOOL_USE if late == TOOL_SEARCH_CALL else WEB_SEARCH_CALL,
                payload=dict(item),
            )
        # Upstream says on the closing event whether this item is whole: `status: "incomplete"` on the one it cut short, `"completed"` on the rest. Measured 15 times, four of them on a `function_call`, whose `arguments` are then truncated JSON.
        #
        # Held rather than dropped, and only when something whole came before it. Half a sentence is not what the client asked for, but it still beats an empty answer, so the rule reverses when this is all there is — and whether it is dropped at all depends on an ending this side has not been told about yet. Ruled 2026-08-21, narrowed 2026-08-22.
        #
        # A `reasoning` item carries no `status` at all — verified against a completed one, whose key set is identical — so this cannot see a truncated one and does not try. Left open deliberately; `.dev/docs/upstream/retry-and-continuation/deferred.md` §2.
        cut_short = _upstream_cut_this_item_short(data) and self._terminal.blocks > 0
        kind = draft.kind
        reasoning = None
        if draft.kind == DISCARDED:
            # Recognised and deliberately not delivered — see the item map for which items land here and why. The point of naming them is that they never reach the text fallback, which would turn each into an empty block.
            return ()
        if draft.kind == UNKNOWN:
            # **Refused, not rendered and not dropped.** `spec.md`'s response matrix requires `REJECT` for an unknown output item, and spells out that it must not be masked by an empty text block or by a normal terminal — naming, in one line, exactly what the two legs each used to do instead.
            #
            # Reported through `failure` rather than raised, because the delivery loop already knows how to end a stream this way and does it correctly: blocks completed before this one go out first — they arrived, and what a client received should not depend on when the refusal landed — then the error frame, then **no terminal**, which `.dev/docs/error-envelope/spec.md` §3.5 requires of a turn that will not succeed. Raising instead would tear the stream, which is the defect rather than the fix.
            #
            # `replayable=False`: this is our refusal, not upstream's report, so there is no upstream event to hand a direct client. The framer spells it on either leg.
            item_type = str(cast(dict[str, Any], data.get("item") or {}).get("type", "")) or "?"
            logger.warning(
                "refusing an output item this proxy cannot carry: type=%r item_id=%r",
                item_type,
                str(draft.payload.get("id", "")),
            )
            self._failure = StreamFailure(
                event="error",
                raw_data="",
                origin=FailureOrigin.PROXY_REFUSAL,
                info=ErrorInfo(
                    # **`NOT_IMPLEMENTED`, not `UPSTREAM`.** The category is not "which side did the bytes come from" — it is what the client can do differently, and the two answers differ: `UPSTREAM` means upstream failed, is a 502, and is retryable by default; `NOT_IMPLEMENTED` means this proxy never built the crossing being asked for, is a 501, and explicitly is not. This item is a legal one the SDK declares, and `UNKNOWN` is this side recognising that it cannot convert it — the same capability gap as `TranslatorNotFound`, not an upstream fault. Filing it as `UPSTREAM` would tell a client to retry something that will never work, and send whoever reads it to the wrong side.
                    #
                    # The status code is the one this category *would* have carried had the failure happened before the headers went out. Nothing rewrites the response: it was fixed at 200 when upstream's headers arrived, and neither SSE writer reads this field. What carries the meaning after that point is `code`, which stays specific — `.dev/docs/error-envelope/spec.md` §6.4.
                    #
                    # `source_format` is left empty on purpose. It names the dialect an error was *read from*, and this one was not read from anything; it is a refusal this proxy formed.
                    category=ErrorCategory.NOT_IMPLEMENTED,
                    message=f"upstream sent an output item this proxy cannot convert: {item_type}",
                    status_code=STATUS_FOR_CATEGORY[ErrorCategory.NOT_IMPLEMENTED],
                    code="unknown_output_item",
                ),
            )
            return ()
        if draft.kind == TOOL_USE:
            self._saw_tool_call = True
            item_kind = str(draft.payload.get("type", ""))
            if item_kind == TOOL_SEARCH_CALL:
                # Two differences from a `function_call`, both of them wire facts rather than preferences: the item carries no name, and its `arguments` are already an object where a function call spells them as a JSON string.
                #
                # **Read off the closing event, not the draft** — the same trap the web-search branch below documents. `output_item.added` carries this item with only an id, a type and a call id; the arguments appear for the first time on `done`, and there are no delta events to accumulate. Reading the draft yields an empty object, which is what the first version of this did.
                closing = data.get("item")
                arguments = (
                    cast(dict[str, Any], closing).get("arguments")
                    if isinstance(closing, dict)
                    else draft.payload.get("arguments")
                )
                source = cast(dict[str, Any], closing) if isinstance(closing, dict) else draft.payload
                payload: dict[str, Any] = {
                    "type": TOOL_USE,
                    "id": str(source.get("call_id") or source.get("id", "")),
                    "name": self._client_search_tool,
                    "input": arguments if isinstance(arguments, dict) else {},
                }
            else:
                payload = {
                    "type": TOOL_USE,
                    "id": str(draft.payload.get("call_id") or draft.payload.get("id", "")),
                    "name": str(draft.payload.get("name", "")),
                    "input": decode_json(draft.partial_json or "{}"),
                }
        elif draft.kind == THINKING:
            raw_closing = data.get("item")
            closing = (
                dict[str, Any](cast(dict[str, Any], raw_closing))
                if isinstance(raw_closing, dict)
                else {}
            )
            if "summary" not in closing:
                closing["summary"] = self._summary_from_draft(draft)
            if (
                "encrypted_content" not in closing
                and "encrypted_content" in draft.payload
            ):
                closing["encrypted_content"] = draft.payload["encrypted_content"]
            closing["type"] = "reasoning"
            reasoning = read_responses_reasoning(closing)
            payload = reasoning_to_anthropic(reasoning, bridge_for_client=True)
        elif draft.kind == WEB_SEARCH_CALL:
            # Read off the closing event, not the draft. `output_item.added` carries this item with only an id, a status and a type — the query appears for the first time on `done`, and this item has no delta events at all, so the draft has nothing in it to render. Assembling from the draft is what produced an empty text block on every search.
            raw = data.get("item")
            item = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
            payload = {"type": TEXT, TEXT: web_search_call_text(item.get("action"))}
            # Text, until §5.3's block pair is built. Not because the item has no Anthropic spelling — it has one — but because the pair's `content` comes from the `url_citation` annotations on the *next* item, which this does not read yet. See the module docstring.
            kind = TEXT
        else:
            payload = {"type": TEXT, TEXT: draft.text}
        block = CompletedBlock(
            index=self._emitted,
            kind=kind,
            payload=payload,
            reasoning=reasoning,
        )
        self._emitted += 1
        if cut_short:
            # Not recorded either: a block nobody has received is not a block delivered, and whether anyone ever will is decided on the terminal event.
            self._cut_short = block
            return ()
        self._terminal.record(block)
        return (block,)

    def _read_terminal(self, kind: str, data: dict[str, Any]) -> None:
        read_responses_terminal(kind, data, self._terminal, saw_tool_call=self._saw_tool_call)


def read_responses_terminal(
    kind: str, data: dict[str, Any], terminal: Terminal, *, saw_tool_call: bool
) -> None:
    """Fill in what upstream said when it finished.

    Module-level and shared with the direct leg's passthrough for the same reason `responses_failure_from` is: both legs read the same terminal event for the same facts. The passthrough only ever *records* them — `spec.md` §6.3 requires upstream's own terminal to reach the client verbatim, so nothing here is derived back onto the wire, and this is the §10 side record.

    `saw_tool_call` is the one fact the caller has to supply, because the two legs establish it differently: the translating assembler knows it built a tool-use block, and the passthrough knows an item asked the client to act (§7.1). Both mean the same thing to whoever reads the stop reason.

    **The guard is here rather than at each call site**, and it was not here when this function was extracted. The translating assembler had it outside, in a `kind in {...}` branch; the passthrough leg then called this for *every* envelope event, so `response.created` set `seen=True` and `stop_reason="end_turn"` before upstream had said anything at all. Everything downstream that asks "did upstream finish" then answered yes: a torn stream broke out of the delivery loop as an orderly ending, no error frame was written, the exception was swallowed, and replay was never even asked. Measured across three endings; the leg reported a clean `ok` for each. Putting the guard in the shared function is what stops the third caller repeating it.
    """
    if kind not in {"response.completed", "response.incomplete"}:
        return
    terminal.seen = True
    raw = data.get("response")
    response = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    usage = response.get("usage")
    if isinstance(usage, dict):
        terminal.usage = _anthropic_usage(cast(dict[str, Any], usage))
        # Kept as it arrived, for the leg that has to report it back in upstream's own shape. See `Terminal.upstream_usage`.
        terminal.upstream_usage = dict[str, Any](cast(dict[str, Any], usage))
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
        terminal.stop_reason = (
            "max_tokens" if reason == "max_output_tokens" else reason or "incomplete"
        )
        return
    terminal.stop_reason = TOOL_USE if saw_tool_call else "end_turn"


def _upstream_cut_this_item_short(data: dict[str, Any]) -> bool:
    """Whether upstream said, on this closing event, that the item it is closing is not whole.

    `str()` is not used on the way in: an absent field and a null one both mean upstream said nothing, and `str(None)` is the four characters `None`, which is not `"incomplete"` but is also not a value upstream ever sent.
    """
    raw = data.get("item")
    item = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    status = item.get("status")
    return status == "incomplete"


def _anthropic_usage(usage: dict[str, Any]) -> dict[str, Any]:
    """Responses token counts in the keys every reader of this record already expects.

    Stored converted rather than raw because `Terminal.usage` is read as Anthropic reports it, and a Responses usage read that way is not merely missing the cache fields: its `input_tokens` *includes* what came from cache, so a mostly-cached prompt is reported as having been sent whole. The conversion is the one the buffered path already does, reused rather than repeated — the subtraction is the load-bearing part and two copies of it would drift.

    A malformed usage yields no counts instead of propagating. This runs on the terminal event of a stream whose blocks have already been delivered, and the numbers it produces are for a log line: aborting a delivered response over a field nobody is waiting on would trade a working reply for a cosmetic one.
    """
    try:
        return dict[str, Any](anthropic_usage_from_responses(usage))
    except ResponseConversionError:
        return {}
