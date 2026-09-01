"""What every assembler is, and what every assembler produces.

The generic half of reading an upstream. A `BlockAssembler` turns one upstream's events into `CompletedBlock`s; which upstream that is lives in `formats`, one module per wire format, and nothing here knows how many there are.

Its mirror on the way out is `framing`. The two are separate questions and a route answers them differently: a request that arrives as Anthropic Messages and is served by a Responses upstream is assembled by the Responses assembler and framed by the Anthropic framer.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

import orjson

from app.errors import ErrorInfo
from app.pipeline.delivery.blocks import THINKING, TOOL_USE, CompletedBlock, DeliveryUnit
from app.pipeline.delivery.sse_source import SseEvent


class ReplyDialect(StrEnum):
    """Whose vocabulary the reply arrived in.

    Not `WireFormat`. That enum is the whole taxonomy of body shapes a route can take, and it lives with `RequestContext`, which now holds one of these records — importing it here would close a cycle. What a summary of a reply needs is narrower anyway: only which of the two upstreams described it, so the words on the console line can be that upstream's own. A reply is assembled by exactly one of them, so this is a property of the record rather than something a reader has to be told separately.
    """

    ANTHROPIC = "anthropic"
    RESPONSES = "responses"


@dataclass(slots=True)
class Terminal:
    """What the upstream said when it finished."""

    # Empty until an upstream says otherwise, so the field cannot be read as a claim nobody made. It used to default to `end_turn`, which made "upstream said the turn ended cleanly" and "upstream never said anything" the same value — and the console line, which prints this, could not tell them apart either. Whoever has to put a reason on the wire for a stream that ended without one synthesises it there, where the synthesis is visible; see `stream_delivery`.
    stop_reason: str = ""
    usage: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    # Whether the upstream's own terminal event arrived — `message_stop` here, `response.completed` / `response.incomplete` on the Responses side. False means the stream stopped mid-turn, and everything this record does *not* carry is unknown rather than absent.
    seen: bool = False
    # Which upstream described this reply, and so which words the console line should use for it. Anthropic by default because that is also the shape a translated reply is read back in.
    dialect: ReplyDialect = ReplyDialect.ANTHROPIC
    # Every complete content block received before the terminal event, or before the upstream stopped. A count here remains truthful for a truncated turn because only `record()` advances it.
    blocks: int = 0
    # Every tool the model asked for, in the order it asked, duplicates kept. `tool_use` on its own says a turn ended in tool calls; which tools, and how many of each, is the part that tells one turn from another when reading a log.
    tools: list[str] = field(default_factory=lambda: list[str]())
    # Thinking blocks by kind: `txt` carried readable reasoning, `enc` carried only an opaque signature. The distinction is the interesting one — a turn that reasoned and a turn that was handed back sealed reasoning cost the same tokens and look identical from the outside.
    thinking: list[str] = field(default_factory=lambda: list[str]())
    # Upstream's own usage object, kept beside the converted one rather than derived back from it. `usage` above has been through `_anthropic_usage`, which subtracts the cached part of the input and drops `reasoning_tokens` outright — a lossy pass that is right for an Anthropic client and has no inverse. A leg that has to report what upstream actually said needs the original, and reconstructing it would compose two lossy passes into a number neither side ever computed.
    #
    # `None` on every leg but the Responses streaming one, the buffered path included — and `None` rather than an empty mapping, because those are different answers. A usage of zero is a measurement; not having asked is not. An empty default would have made "upstream reported nothing" and "nobody looked" the same value, which is the defect `stop_reason`'s empty default exists to avoid, one field further down.
    upstream_usage: dict[str, Any] | None = None

    def record(self, block: CompletedBlock) -> None:
        """Take one finished block into the running summary of the reply.

        Classification lives here, on the record itself, rather than at each place a block becomes final. There are three such places — the two assemblers and a buffered reply read back whole — and when each did its own classifying, the same question ("was this reasoning readable?") was answered by three separate expressions that were free to drift apart. Reading the block's own payload, rather than whatever local draft produced it, is what lets one implementation serve all three.
        """
        self.blocks += 1
        if block.kind == TOOL_USE:
            self.tools.append(str(block.payload.get("name", "")))
        elif block.kind == THINKING:
            self.thinking.append("txt" if block.payload.get(THINKING) else "enc")


class FailureOrigin(StrEnum):
    """Who decided this turn will not succeed.

    The load-bearing distinction behind `StreamFailure`, and it has no safe default — which is why it is a required field and an enum rather than a defaulted bool. It was a bool called `replayable` for one commit, and that name collided with `ReplaySupport` in the delivery loop, which answers an entirely different question (may this *attempt* be retried).
    """

    # Upstream said so, in its own event. A client that speaks upstream's dialect can be handed those words unchanged.
    UPSTREAM_EVENT = "upstream_event"
    # This proxy said so. There is no upstream event behind it, so there is nothing to replay on any leg and the client's framer has to spell it.
    PROXY_REFUSAL = "proxy_refusal"


@dataclass(frozen=True, slots=True)
class StreamFailure:
    """This turn will not end successfully, and the stream is already open.

    Carried rather than returned from `push`, for the same reason `terminal` is: it is a fact about the stream so far, not a block that just completed, and threading it through the return type would make every caller destructure a tuple to ask a question most of them do not have.

    **Two origins, and they are not interchangeable.** `origin` is which. An upstream failure on a direct leg goes back out as `event` and `raw_data` arrived — upstream's own event name, upstream's own payload, including the fields nothing here recognises — and only the SSE wrapper is rebuilt. A translated leg cannot do that; the client does not speak that dialect, so it gets `info` spelled in its own. A refusal this proxy formed has no upstream event to replay **on either leg**, so it always goes through the framer.

    `origin` has no default deliberately. Omitting it would silently pick "upstream's own words", and the next construction site added for a proxy-side refusal would then try to replay an empty payload under upstream's event name — failing open, on the field that decides which of two mutually exclusive things this is.

    `raw_data` is the undecoded payload text, not a re-serialised dict. Round-tripping through `orjson` preserves the fields and not the bytes, and "even if we do not know it, it can still be passed on" is about the bytes. It is empty on a `PROXY_REFUSAL`, and nothing reads it there.
    """

    event: str
    raw_data: str
    info: ErrorInfo
    origin: FailureOrigin


class BlockAssembler[UnitT: DeliveryUnit = CompletedBlock](Protocol):
    """Turns one upstream's events into whatever that leg delivers.

    Generic over the unit since 2026-08-31. The translating legs produce `CompletedBlock`; the direct Responses leg produces a run of upstream's own events, because on that leg the client speaks upstream's dialect and there is nothing to translate. Both satisfy this, so `stream._deliver` reads one shape and needs no branch for which leg it is serving.
    """

    def push(self, event: SseEvent) -> tuple[UnitT, ...]:
        """Take one event; return units that just became deliverable."""
        ...

    @property
    def terminal(self) -> Terminal: ...

    @property
    def failure(self) -> StreamFailure | None:
        """Why this turn will not succeed, when something has decided that.

        Two things can decide it, and `StreamFailure.origin` says which: upstream reported the failure in its own event, or this proxy refused something it cannot convert. The second was added 2026-08-30 for unknown output items; before that this property carried only the first, and its contract said so.

        `None` on every stream where neither has happened, which includes a stream that simply stopped — that is a different ending and `cut_mid_block` is what tells those apart.

        Until 2026-08-24 both assemblers logged an upstream failure event and returned nothing, so `terminal.seen` stayed false and the client received whatever the terminal-less path produces. Since the clean-EOF change of 2026-08-22 that path is a *successful-looking* ending, which made an upstream failure indistinguishable from a completed turn.
        """
        ...

    def close(self) -> tuple[UnitT, ...]:
        """Whatever this assembler is still holding that the ending may deliver.

        `()` for the translating assemblers: what they hold is a half-built block, and `spec.md` §3 drops those at every ending — there is nothing an ending could legally take from them.

        The direct passthrough holds something else. Its queue keeps whole, finished item groups behind an earlier item that never closed, and those are not half-built: dropping them threw away the entire response, upstream's own terminal included, whenever any item failed to close. `direct-passthrough/spec.md` §7.2's closing sequence says which of the held events go and which stay, and this is where the caller asks.
        """
        ...

    @property
    def queued_bytes(self) -> int:
        """Bytes this assembler is holding that the delivery buffer cannot see.

        `0` for the translating assemblers, and that is the pre-existing accounting rather than a claim they hold nothing: their drafts become blocks at the item's closing event and enter the buffer there, so the cap sees them from that point. A draft mid-item has never been counted and this change does not alter that.

        The passthrough's queue is different in kind, which is why the field exists: an item that opens and does not close holds every later group behind it, and `spec.md` §8 names exactly those — "尚未 `done` 的原始事件队列、已完成但被 policy 扣住的事件组" — as the first thing the cap must count. Left uncounted, `buffer_cap_bytes` bounded nothing on this leg.
        """
        ...

    @property
    def cut_mid_block(self) -> bool:
        """Whether a block was still being accumulated when the events stopped.

        The one observable that tells a stream cut *between* blocks from one cut *through* one. Both leave `terminal.seen` false, and until this existed the two were answered identically — an upstream that closed cleanly after finishing its last block was reported to the client as a truncation, the same as one severed mid-sentence.

        Deliberately not "did the client get whole blocks". Under block-level delivery that question is always yes: a half-built block is never handed downstream, so it cannot discriminate anything. What is being asked here is about the *assembler's* state, which is the only place the difference survives.
        """
        ...


@dataclass(slots=True)
class Draft:
    """One block being accumulated, before its closing event arrives.

    Public rather than private because both formats' assemblers build one, and one of them passes it to a helper of its own. A second copy per format would be two places for the same shape to drift.
    """

    index: int
    kind: str
    payload: dict[str, Any]
    text: str = ""
    partial_json: str = ""


def decode_json(raw: str) -> Any:
    """A tool call's accumulated arguments, or a marker holding the text that would not parse.

    Shared by both assemblers, which is why it is not private. `{"__raw": …}` is the marker; whatever reads a block back out has to know about it, and `openai_responses`'s framer does.
    """
    try:
        return orjson.loads(raw)
    except orjson.JSONDecodeError:
        # Keep the text rather than dropping it; a malformed argument is still evidence.
        return {"__raw": raw}
