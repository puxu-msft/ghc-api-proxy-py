"""Direct-leg passthrough: group upstream's own events, hand them back unchanged.

**One engine, one vocabulary per dialect.** `spec.md` §2.5: the *mechanism* here is dialect-independent — finding boundaries, holding a prefix until it is whole, keeping the original order, refusing to deliver a control-only prefix on its own — so the engine lives here once and each direct format supplies a `Dialect` describing its own wire. Copying the engine per format would put the same nine rounds of rulings in two places to drift.

What is **not** dialect-independent, and the Spec said it was until v14: several of its clauses only ever wrote one dialect's values. §5.2's failure-to-`RetryReason` table keys on `ResponseError.code`, which Anthropic's error event does not have at all — that leg needs a table of its own and does not have one yet (`deferred.md` D-6).

Why the path exists at all, in one line: on a same-format direct request the client speaks upstream's dialect, so mapping an item into an Anthropic block and back is a round trip whose only consumer is the framer that undoes it — and GitHub issues #1, #2 and #3 all landed on a loss point of that trip. `spec.md` §1 has the long version, §2.6 walks the four direct legs.

**What this deliberately does not know: item types.** There is no type table here and there must not be one. `Dialect` describes *boundaries and attribution* — which events are the envelope, what keys an item, what closes one — and never taxonomy, so an item this proxy has never heard of is carried without anything having to recognise it. A type table would rebuild the ceiling §2.1 rules out.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from app.errors import ErrorInfo
from app.pipeline.delivery.assembling import ReplyDialect, StreamFailure, Terminal
from app.pipeline.delivery.framing import OutboundFramer
from app.pipeline.delivery.sse_source import SseEvent, encode_frame

logger = logging.getLogger(__name__)


class Attribution(StrEnum):
    """Where an event belongs when it belongs to no output item.

    Two values rather than one `None`, because `spec.md` §4 gives them **opposite** treatments: an envelope event travels with the prefix it sits in, while an event this proxy cannot attribute is held. Collapsing both into a single `None` made an unattributable event indistinguishable from an envelope one, and it was released as though it were envelope.

    Not hypothetical. Of the 58 members of `ResponseStreamEvent` in `openai==3.3.1`, eleven carry no `output_index`; seven are the envelope, and the remaining four — the `response.audio.*` series — carry model output with neither an index nor an item id. A payload that fails to parse lands here too, since `SseEvent.json()` answers `{}`.
    """

    ENVELOPE = "envelope"
    UNATTRIBUTED = "unattributed"


@dataclass(frozen=True, slots=True)
class Dialect:
    """What the engine cannot derive about one wire format.

    `spec.md` §2.5 holds the same list and is the authority for it. **Deliberately not stated as a count here**: the docstring said "the six facts" while the class already had eight fields, and the Spec's table said six as well — a number transcribed into two places is a number nobody updates when a field is added, and both copies were behind by two before anyone noticed.

    Every field answers a boundary or attribution question. None of them names an item type, which is §2.1's consequence rather than a style choice: a type table rebuilds the ceiling the whole topic exists to remove.
    """

    # What the completion line and the observability record call this leg.
    name: str
    # Which vocabulary the completion line should judge this reply by. Load-bearing rather than cosmetic: `RECEIVED_BYTES_THRESHOLDS` differs by an order of magnitude between the two, so a Responses reply left at the default was coloured heavy at 120KiB while the same bytes on the translating leg read as ordinary.
    reply_dialect: ReplyDialect
    # Events belonging to no output item. `spec.md` §5 governs when they may be submitted.
    control_events: frozenset[str]
    # The control events that end the response. §5's commit table gives an item-less terminal its own row, and that row is what lets one of these release a prefix with no item events in it — otherwise the shortest legal response, envelope then terminal, would be held forever.
    #
    # Cited by what the row says rather than by where it sits: the position was written as "fourth row" in four places and was off by one in all of them, because a row's number is exactly the kind of fact that goes stale and never fails a test.
    terminal_events: frozenset[str]
    # The event that declares one output item complete.
    item_done_event: str
    # The payload field that says which item an event belongs to. Responses keys on `output_index`, Anthropic on `index`; both are positions rather than ids, which matters because Copilot sends a different item id on an item's opening and closing events.
    item_index_field: str
    # Whether a finished item stops the turn until the client submits a tool output or an approval (`spec.md` §7.1).
    requires_client_action: Callable[[dict[str, Any]], bool]
    # Fill in the observable terminal facts from a terminal event. §10 wants the authoritative status and usage; the wire still carries upstream's own event verbatim, so nothing here is reverse-derived onto it (§6.3).
    read_terminal: Callable[[SseEvent, Terminal, bool], None]
    # Upstream's own failure event, as a failure record, or `None` when this event is not one.
    read_failure: Callable[[SseEvent], StreamFailure | None]


def _event_bytes(event: SseEvent) -> int:
    """What holding one event costs, measured on the text actually held.

    The single definition both `RawEventBatch.size_bytes` and `PassthroughAssembler.queued_bytes` call, so §8's measure has one place to change. Measured on the raw event text rather than on `repr` of a parsed payload: what this path holds is exactly these strings.

    An approximation of the wire, and a good one — over the 125 real events of `history_responses_stream.json` this gives 51710 against 53710 actually framed, 1.04x, because it omits the field names and separators `encode_frame` adds.
    """
    return len(event.event.encode()) + len(event.data.encode())


@dataclass(frozen=True, slots=True)
class RawEventBatch:
    """A run of upstream events that may go to the client now, in the order they arrived.

    Not a `CompletedBlock`. That type is "one fully materialised **Anthropic** content block", and nothing on this path is Anthropic-shaped — putting raw events inside it would be the same category error the round trip already made once.

    A batch is a *safe prefix*, not one item: `spec.md` §4 releases everything up to the point where some item is still open, so one batch can carry several items' events plus the control events between them. That is what keeps the original order without reordering anything.

    It satisfies `DeliveryUnit`, which is what lets the ordinary `BlockBuffer` hold it and apply the three policies without knowing what is inside.
    """

    events: tuple[SseEvent, ...]
    dialect: Dialect

    @property
    def size_bytes(self) -> int:
        """What holding this costs, per `spec.md` §8. See `_event_bytes`."""
        return sum(_event_bytes(e) for e in self.events)

    @property
    def requires_client_action(self) -> bool:
        """Whether any item in this batch stops the turn until the client acts.

        **Read off whichever event carries the item object, not off the closing event.** The two dialects put it in different places: a Responses `output_item.done` carries the finished item, while an Anthropic `content_block_stop` carries only an index and the block's type arrived on `content_block_start`. Asking only the closing event would answer `False` for every Anthropic tool call.

        Safe to scan the whole batch because §4 already guarantees an item's events never straddle a release boundary: if the item is in here at all, its whole group is. Where a dialect spreads the deciding fields across events — a Responses `tool_search_call` announces its type on the opening event and its `execution` on the closing one — `any` takes the conservative direction, which is the same direction §7.1 takes for an unknown type.
        """
        return any(
            self.dialect.requires_client_action(item)
            for item in (_item_object(e) for e in self.events)
            if item
        )

    @property
    def contains_terminal(self) -> bool:
        """Whether this batch carries upstream's own terminal event.

        Asked on the structured batch rather than by searching the encoded bytes. A payload may repeat an event name as data, and each dialect already owns the authoritative terminal set.
        """
        return any(event.event in self.dialect.terminal_events for event in self.events)

    def encode(self) -> bytes:
        """The batch as SSE frames, each event's name and payload unchanged.

        `encode_frame` rather than a JSON re-serialisation: the payload goes back out as the text it arrived as, and a round trip through an encoder keeps the fields and not the bytes. Multi-line payloads survive because that encoder writes one `data:` field per line.
        """
        return b"".join(encode_frame(e.event, e.data) for e in self.events)


def _item_object(event: SseEvent) -> dict[str, Any]:
    """The item object an opening or closing event carries, or an empty mapping.

    Empty rather than `None` so callers ask about its contents rather than about whether it exists — an item with no readable type gets the same conservative answer an unknown one does.
    """
    for key in ("item", "content_block"):
        found: object = event.json().get(key)
        if isinstance(found, dict):
            return dict[str, Any](found)  # pyright: ignore[reportUnknownArgumentType]
    return {}


@dataclass(slots=True)
class _Pending:
    """One event in the queue, and what it belongs to.

    `item` is the item's *position* for an item event — never its id, for the reason `ResponsesAssembler._item_key` already records: this upstream sends a different id on an item's opening and closing events, so keying on the id pairs nothing. Otherwise it is an `Attribution`, and which of the two decides whether the event may be released.
    """

    event: SseEvent
    item: int | Attribution
    # Whether this event goes out inside a batch. False for an upstream failure event: `stream._report_failure` replays that one verbatim as the stream's last frame, and a copy in the batch would deliver it twice. It stays in the queue regardless, because §5's item-less-terminal row uses it to lift the hold on a control-only prefix.
    emit: bool = True


class PassthroughAssembler:
    """Groups upstream's events into safe prefixes without interpreting them.

    **One per attempt, not one per request.** `spec.md` §5 discards the old attempt's queue, ids, terminal and accounting when a replay opens a new one, and `_closed` here is permanent — feeding a second attempt's events to the same instance would find its indices already closed, so nothing would ever be held and block-level delivery would silently degrade to per-event forwarding. There is deliberately no `reset`: an attempt gets a new assembler.

    Satisfies `BlockAssembler[RawEventBatch]`, so `stream._deliver` reads one shape and needs no branch for which leg it is serving.
    """

    def __init__(self, dialect: Dialect) -> None:
        self._dialect = dialect
        self._queue: list[_Pending] = []
        # Positions of every item opened and not yet closed. A prefix is safe up to the first event belonging to one of these.
        self._open: set[int] = set()
        # Positions already closed, so a later event carrying one does not reopen it. Within a single attempt this cannot happen — the closing event is an item's last — which is why the class is per-attempt: across attempts it can, and would.
        self._closed: set[int] = set()
        self._terminal = Terminal(dialect=dialect.reply_dialect)
        self._failure: StreamFailure | None = None
        self._saw_client_action = False

    def push(self, event: SseEvent) -> tuple[RawEventBatch, ...]:
        """Take one event; return whatever may now be delivered.

        Returns at most one batch, because a release always takes the longest safe prefix there is.

        The observable facts are read on the way past. They never touch the wire: §6.3 requires upstream's own terminal to be replayed verbatim, so `Terminal` here is a §10 side record and nothing is derived back onto the events.
        """
        item = self._item_of(event)
        self._queue.append(_Pending(event=event, item=item))
        if isinstance(item, int):
            if event.event == self._dialect.item_done_event:
                # A closing event for a position never opened still closes it. Defensive: an item left open would wedge the queue forever, and tolerating it costs nothing. Whether upstream sends that shape is an open question — `hosted-web-search-spec.md` §12 P7, where both of this project's measurements carried an opening event. The regression on record is the reference project's own implementation dropping such an item silently, a different fact about a different program.
                if item in self._closed:
                    # **The one shape that can make a single-slot client render an answer twice**, and this leg forwards it where the translating leg swallowed it. Codex takes an item out of its slot on this event; a second one finds the slot empty, synthesises a fresh started/completed pair, and renders the whole text again as ordinary content — read from its source, not inferred. `deferred.md` D-9.
                    #
                    # **Recorded rather than dropped, because nobody has caught upstream doing it.** Every capture this project holds carries exactly one closing event per item, so the question of whether this ever fires is exactly the question that cannot be answered from what is on disk. Dropping it would change what a native leg promises (§2.1) on the strength of a guess; a log line changes nothing and settles it from one real session.
                    logger.warning(
                        "upstream closed output_index %d twice on the %s leg; a client that keys on one open item at a time will render this item's content again (deferred.md D-9)",
                        item,
                        self._dialect.name,
                    )
                self._open.discard(item)
                self._closed.add(item)
                self._terminal.blocks += 1
                if self._dialect.requires_client_action(_item_object(event)):
                    self._saw_client_action = True
            elif item not in self._closed:
                self._open.add(item)
        if item is Attribution.ENVELOPE:
            # **Every** envelope event, not only the terminal ones. Anthropic splits its ending in two — `message_delta` carries the stop reason and usage, `message_stop` merely closes — so reading facts only off terminal events would drop half of what §10 asks for on that leg. Each dialect's reader ignores the envelope events it has nothing to say about, and that ignoring is the reader's own job: when it was left to the call sites, one of them forgot.
            self._dialect.read_terminal(event, self._terminal, self._saw_client_action)
            failure = self._dialect.read_failure(event)
            if failure is not None:
                self._failure = failure
                # Carried by `stream._report_failure`, which replays it verbatim as the last frame. Emitting it here as well delivered upstream's failure to the client twice, byte-identically — a new behaviour this leg introduced, since the translating leg only ever produced the one frame.
                self._queue[-1].emit = False
        released = self._take_safe_prefix()
        return (released,) if released is not None else ()

    @property
    def terminal(self) -> Terminal:
        return self._terminal

    @property
    def failure(self) -> StreamFailure | None:
        return self._failure

    @property
    def cut_mid_block(self) -> bool:
        """Whether an item was still open when the events stopped. See `BlockAssembler`."""
        return bool(self._open)

    def _item_of(self, event: SseEvent) -> int | Attribution:
        """Which output item an event belongs to, or why it belongs to none.

        Read off the dialect's index field, and **any event carrying one counts** — including event types nothing here has heard of. That is the point: a `response.custom_tool_call_input.delta` is grouped correctly without anything knowing what a custom tool call is.

        An event with no index is envelope only if the dialect names it. Everything else is `UNATTRIBUTED`, a held position rather than a released one.
        """
        if event.event in self._dialect.control_events:
            return Attribution.ENVELOPE
        payload: dict[str, Any] = event.json()
        index = payload.get(self._dialect.item_index_field)
        return index if isinstance(index, int) else Attribution.UNATTRIBUTED

    def _is_barrier(self, pending: _Pending) -> bool:
        """Whether this event may not be released yet, and so stops the prefix.

        Two reasons, and `spec.md` §4 states both. An event of a still-open item cannot go until that item closes. An event this proxy could not attribute is held — it may belong to an item that never closes, and §3 requires exactly those to be dropped at an ending rather than delivered.
        """
        if pending.item is Attribution.UNATTRIBUTED:
            return True
        return isinstance(pending.item, int) and pending.item in self._open

    def _take_safe_prefix(self) -> RawEventBatch | None:
        """The longest prefix that may be released, per `spec.md` §4.

        Three constraints, and only the first is obvious.

        **It stops at the first event that may not go, rather than skipping it.** Skipping would deliver a later item ahead of an earlier one, and reordering is the one thing that makes a sequence number go backwards and an index disagree with the client's snapshot — which is why §4 accepts head-of-line blocking instead.

        **No item's events may straddle the boundary.** §4 defines "already done" as the item's closing event falling inside the prefix, not merely the item's state being closed. Without that, `created → added(0) → added(1) → delta(1) → done(0)` releases item 0's opening without its closing: half a group to the client, and — the expensive half — it commits the attempt on a byte carrying no content, which shuts §5's replay window for a turn that could still have been replayed intact. The retreat iterates, because each retreat lengthens the tail it is checked against.

        **A prefix of nothing but envelope events is not delivered on its own.** §4: it may *be* a delivery unit and may not be delivered alone; it rides out with the first batch of item events, which is what §5's commit table means by keeping the opening envelope event attempt-local. A terminal lifts the hold (§5's commit table gives an item-less terminal its own row) — otherwise the shortest legal response, envelope then terminal, would be held forever, and there is nothing left to replay once upstream has said how the turn ended.
        """
        cut = len(self._queue)
        for position, pending in enumerate(self._queue):
            if self._is_barrier(pending):
                cut = position
                break
        while cut > 0:
            tail_items = {p.item for p in self._queue[cut:] if isinstance(p.item, int)}
            straddler = next(
                (
                    position
                    for position, p in enumerate(self._queue[:cut])
                    if isinstance(p.item, int) and p.item in tail_items
                ),
                None,
            )
            if straddler is None:
                break
            cut = straddler
        if cut == 0:
            return None
        head = self._queue[:cut]
        if not any(isinstance(p.item, int) for p in head) and not any(
            p.event.event in self._dialect.terminal_events for p in head
        ):
            return None
        del self._queue[:cut]
        emitted = tuple(p.event for p in head if p.emit)
        if not emitted:
            return None
        return RawEventBatch(events=emitted, dialect=self._dialect)

    @property
    def queued_bytes(self) -> int:
        """What is queued and not yet released, for the cap in `spec.md` §8. See `_event_bytes`."""
        return sum(_event_bytes(p.event) for p in self._queue)

    def close(self) -> tuple[RawEventBatch, ...]:
        """`spec.md` §7.2's closing sequence, applied to whatever is still queued.

        Step 1 drops an unclosed item's events: a terminal proves the response ended, not that an item without a closing event became whole. Step 2 keeps the control events and every completed group in their original order — those were only being held by head-of-line blocking, and dropping them was throwing away finished content the client is owed. Step 3 keeps the unattributable events only when no item is unclosed; with one open, an unattributable event may be the missing half of it and delivering it would emit an orphan.

        Returns at most one batch. Before this existed the queue was simply abandoned at every ending, so a single item that never closed produced a 200 with zero bytes — upstream's own `response.completed` included.
        """
        open_items = set(self._open)
        drop_unattributed = bool(open_items)
        kept = tuple(
            p.event
            for p in self._queue
            if p.emit
            and not (isinstance(p.item, int) and p.item in open_items)
            and not (p.item is Attribution.UNATTRIBUTED and drop_unattributed)
        )
        self._queue.clear()
        self._open.clear()
        return (RawEventBatch(events=kept, dialect=self._dialect),) if kept else ()

    @property
    def unfinished_items(self) -> tuple[SseEvent, ...]:
        """Events of items that opened and never closed. **Every** ending drops these.

        `spec.md` §3 says why the alternative was impossible: a terminal proves the response ended, not that an item without a closing event became whole. Exposed rather than dropped here because *when* to drop is the ending's decision, not the assembler's.
        """
        return tuple(
            p.event for p in self._queue if isinstance(p.item, int) and p.item in self._open
        )

    @property
    def unattributed(self) -> tuple[SseEvent, ...]:
        """Events belonging to no item this proxy could identify. **Their disposal at an ending is not the same as `unfinished_items`'.**

        Where they go is `spec.md` §7.2's closing sequence to decide, and this property deliberately does not say what that answer is — an earlier version transcribed the rule into this docstring, the rule was then found wrong, and a copy in the code is one more place a correction has to reach. What is settled here, and independent of that answer, is that the two classes are reported **apart**: an unclosed item is known to exist and known not to have finished, while these are not known to belong to any item at all, and one property returning both let the second inherit a disposal reason that does not apply to it.

        Held exactly like `unfinished_items` in the meantime, because releasing one while holding the other would reorder.
        """
        return tuple(p.event for p in self._queue if p.item is Attribution.UNATTRIBUTED)


@dataclass(slots=True)
class PassthroughFramer:
    """Writes batches out, and delegates everything this leg still has to invent.

    **Holds no renumbering state, because there is nothing to renumber.** Every counter a translating framer maintains — sequence numbers, output indices, minted ids — exists to build events this proxy is inventing. Here it invents none, so it keeps none; `spec.md` §3 and §6.2 forbid rewriting any of them.

    **`preamble` and `terminal` are empty on purpose, and they are not the same emptiness.** Upstream's own opening envelope event and its own terminal arrive as ordinary events and ride out inside batches, so emitting counterparts here would deliver each of them twice — with different ids, since the invented one is not upstream's.

    **`error` and `keepalive` are delegated rather than reimplemented.** Those two frames really are this side's inventions, and each dialect already spells them: an SSE comment for the keep-alive, and the error shape `error-envelope/spec.md` §6.3 sets out. Writing a second copy here would be one more place for the two spellings to drift, so the leg's ordinary framer supplies them.

    **`reshape` is the one place a declared compatibility contract may edit the wire**, and it is `None` unless an operator switched one on. §2.7 requires such a transform to be named, optional and never called native; keeping it as a parameter rather than a branch inside `block` is what stops it becoming an unnamed default the way stable ids did before `1fb37cd` (§6.6.6). The engine stays dialect-agnostic: whichever vocabulary is in play supplies the callable, or does not.
    """

    delegate: OutboundFramer[Any]
    reshape: Callable[[tuple[SseEvent, ...]], tuple[SseEvent, ...]] | None = None
    on_terminal_unit: Callable[[], None] | None = None

    @property
    def synthesises_terminal(self) -> bool:
        """No: `spec.md` §8 forbids this leg inventing a successful terminal.

        Read by `stream._deliver` at the one ending where a terminal would otherwise be synthesised — upstream closed cleanly between items without saying how the turn ended. On a translating leg the configured stop reason is written there and the turn reads as complete. On this leg §5.1 requires an error instead: the client is owed the truth that upstream never finished, and there is no honest terminal to write because the only honest one is upstream's, which never arrived.
        """
        return False

    def preamble(self) -> tuple[bytes, ...]:
        return ()

    def block(self, block: RawEventBatch) -> tuple[bytes, ...]:
        if self.reshape is not None:
            block = replace(block, events=self.reshape(block.events))
        encoded = block.encode()
        if block.contains_terminal and self.on_terminal_unit is not None:
            # The caller confirms this frontier only after the yielded chunk's ASGI send returns. Marking here says which chunk carries the terminal; it does not claim that the client has it yet.
            self.on_terminal_unit()
        return (encoded,)

    def terminal(self, terminal: Terminal) -> tuple[bytes, ...]:
        return ()

    def error(self, info: ErrorInfo) -> bytes:
        return self.delegate.error(info)

    def keepalive(self) -> bytes:
        return self.delegate.keepalive()
