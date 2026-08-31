"""Direct Responses passthrough: group upstream's own events, hand them back unchanged.

**Skeleton.** This is step 2 of `.dev/docs/direct-responses-passthrough/plan.md` — the assembler and framer exist and are unit-testable, and **nothing is wired to them**. `delivery_policy` still routes every Responses stream through `ResponsesAssembler`. Wiring, and the revocation of the direct leg's `REJECT` that goes with it, are one later step, because they are one observable switch.

Why this module exists at all, in one line: on a same-format direct request the client speaks upstream's dialect, so translating the item into an Anthropic block and back is a round trip whose only consumer is the framer that undoes it — and both GitHub issues #1 and #2 landed on a loss point of that trip. `spec.md` §1 has the long version.

**What this deliberately does not know.** Item types. There is no table here and there must not be one: the whole point is that an item this proxy has never heard of reaches the client intact, so recognising types would reintroduce the ceiling the topic exists to remove. What it knows is *boundaries* — which events belong to which output item, and when that item closed — because block-level delivery needs a unit, and `spec.md` §4 makes the unit a safe prefix rather than a single item.

**Not implemented here, by design** (each has its own step): attempt replay and the commit frontier's interaction with it (§5), the three buffering policies and `requires_client_action` (§7), response headers (§9.1), memory cap accounting (§8). This skeleton releases a prefix as soon as it is safe, which is `block` semantics, and holds nothing back for any other reason.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.pipeline.delivery.sse_source import SseEvent, encode_frame


class Attribution(StrEnum):
    """Where an event belongs when it belongs to no output item.

    Two values rather than one `None`, because `spec.md` §4 gives them **opposite** treatments: an envelope event travels with the prefix it sits in, while an event this proxy cannot attribute is *"保守持有到 terminal"* — held, not released. Collapsing both into a single `None` made an unattributable event indistinguishable from an envelope one, and it was released as though it were envelope.

    That is not a hypothetical shape. Of the 58 members of `ResponseStreamEvent` in `openai==3.3.1`, eleven carry no `output_index`; seven are the envelope, and the remaining four — `response.audio.delta`, `response.audio.done`, `response.audio.transcript.delta`, `response.audio.transcript.done` — carry model output with neither an `output_index` nor an `item_id`. A payload that fails to parse lands here too, since `SseEvent.json()` answers `{}`.
    """

    ENVELOPE = "envelope"
    UNATTRIBUTED = "unattributed"


# The response envelope: events that belong to no output item and are safe to release in place. `spec.md` §5 governs when they may be *submitted*; the skeleton only keeps them in their original position.
#
# This is the one name-keyed table in the module, and it stays narrow on purpose: it separates "envelope" from "everything else", never one item type from another. An item event this proxy has never heard of falls into "everything else" and is handled without being recognised, so the ceiling stays removed.
#
# Two facts about this list, both measured against `openai==3.3.1` on 2026-08-31. `response.queued` is in the SDK union and belongs here. `response.cancelled` is **not** in that union, but `spec.md` §5.2 and §6.3 both treat it as a terminal this upstream can send; the SDK's silence says the SDK lacks the type, not that Copilot never emits it, so it stays.
CONTROL_EVENTS = frozenset(
    {
        "response.created",
        "response.queued",
        "response.in_progress",
        "response.completed",
        "response.incomplete",
        "response.failed",
        "response.cancelled",
        "error",
    }
)

_ITEM_DONE = "response.output_item.done"


def _event_bytes(event: SseEvent) -> int:
    """What holding one event costs, measured on the text actually held.

    The single definition both `RawEventBatch.size_bytes` and `ResponsesPassthroughAssembler.held_bytes` call, so that §8's measure has one place to change. Measured on the raw event text rather than on `repr` of a parsed payload: what this path holds is exactly these strings.

    An approximation of the wire, and a good one — over the 125 real events of `history_responses_stream.json` this gives 51710 against 53710 actually framed, 1.04x, because it omits the field names and separators `encode_frame` adds.
    """
    return len(event.event.encode()) + len(event.data.encode())


@dataclass(frozen=True, slots=True)
class RawEventBatch:
    """A run of upstream events that may go to the client now, in the order they arrived.

    Not a `CompletedBlock`. That type is defined as "one fully materialised **Anthropic** content block", and nothing on this path is Anthropic-shaped — putting raw Responses events inside it would be the same category error the round trip already made once.

    A batch is a *safe prefix*, not one item: `spec.md` §4 releases everything up to the point where some item is still open, so one batch can carry several items' events plus the control events between them. That is what keeps the original order without reordering anything.
    """

    events: tuple[SseEvent, ...]

    @property
    def size_bytes(self) -> int:
        """What holding this costs, per `spec.md` §8. See `_event_bytes`."""
        return sum(_event_bytes(e) for e in self.events)

    def encode(self) -> bytes:
        """The batch as SSE frames, each event's name and payload unchanged.

        `encode_frame` rather than `SseFrame`: the payload goes back out as the text it arrived as, and a round trip through a JSON encoder would keep the fields and not the bytes. Multi-line payloads survive because that encoder writes one `data:` field per line.
        """
        return b"".join(encode_frame(e.event, e.data) for e in self.events)


@dataclass(slots=True)
class _Pending:
    """One event in the queue, and what it belongs to.

    `item` is the `output_index` for an item event — **not** the item id, for the reason `ResponsesAssembler._item_key` already records: this upstream sends a different `item.id` on `added` and `done` for the same item, so keying on the id pairs nothing. Otherwise it is an `Attribution`, and which of the two decides whether the event may be released.
    """

    event: SseEvent
    item: int | Attribution


class ResponsesPassthroughAssembler:
    """Groups upstream's events into safe prefixes without interpreting them.

    **One per attempt, not one per request.** `spec.md` §5 discards the old attempt's queue, ids, terminal and accounting when a replay opens a new one, and `_closed` here is permanent — feeding a second attempt's events to the same instance would find its indices already closed, so nothing would ever be held and block-level delivery would silently degrade to per-event forwarding. There is deliberately no `reset`: an attempt gets a new assembler. Replay itself is a later step; the lifetime this class requires is decided here because `_closed`'s permanence is decided here.
    """

    def __init__(self) -> None:
        self._queue: list[_Pending] = []
        # `output_index` of every item that has been opened and not yet closed. A prefix is safe up to the first event belonging to one of these.
        self._open: set[int] = set()
        # Indices already closed, so that a later event carrying one does not reopen it. Within a single attempt this cannot happen — `output_item.done` is an item's last event — which is why the class is per-attempt: across attempts it can, and would.
        self._closed: set[int] = set()

    def push(self, event: SseEvent) -> tuple[RawEventBatch, ...]:
        """Take one event; return whatever may now be delivered.

        Returns at most one batch, because a release always takes the longest safe prefix there is.
        """
        item = _item_of(event)
        self._queue.append(_Pending(event=event, item=item))
        if isinstance(item, int):
            if event.event == _ITEM_DONE:
                # A `done` for an index never opened still closes it. Defensive: an item left open would wedge the queue forever, and tolerating it costs nothing. Whether upstream actually sends that shape is an open question — `hosted-web-search-spec.md` §12 P7, where both of this project's measurements carried an `added`. The regression on record is the reference project's own implementation dropping such an item silently, which is a different fact.
                self._open.discard(item)
                self._closed.add(item)
            elif item not in self._closed:
                self._open.add(item)
        released = self._take_safe_prefix()
        return (released,) if released is not None else ()

    def _is_barrier(self, pending: _Pending) -> bool:
        """Whether this event may not be released yet, and so stops the prefix.

        Two reasons, and `spec.md` §4 states both. An event of a still-open item cannot go until that item closes. An event this proxy could not attribute is held to the terminal — it may belong to an item that never closes, and §3 requires exactly those to be dropped at an ending rather than delivered.
        """
        if pending.item is Attribution.UNATTRIBUTED:
            return True
        return isinstance(pending.item, int) and pending.item in self._open

    def _take_safe_prefix(self) -> RawEventBatch | None:
        """The longest prefix that may be released, per `spec.md` §4.

        Two constraints, and the second is the one a first reading misses.

        **It stops at the first event that may not go, rather than skipping it.** Skipping would deliver a later item ahead of an earlier one, and reordering is the one thing that makes `sequence_number` go backwards and `output_index` disagree with the client's snapshot — which is why §4 accepts head-of-line blocking instead. That applies to an unattributable event too.

        **And no item's events may straddle the boundary.** §4 defines "already `done`" as the item's `done` event falling inside the prefix, not merely the item's state being done, so the cut retreats past any item that also has events in the tail. Without that, `created → added(0) → added(1) → delta(1) → done(0)` releases item 0's `added` without its `done`: half a group to the client, and — the expensive half — it commits the attempt on a byte carrying no content, which shuts §5's whole-attempt replay window for a turn that could still have been replayed intact. Retreating is iterative because each retreat lengthens the tail, which can pull in an item that was fine a moment ago.
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
        taken = self._queue[:cut]
        del self._queue[:cut]
        return RawEventBatch(events=tuple(p.event for p in taken))

    @property
    def held_bytes(self) -> int:
        """What is queued and not yet released, for the cap in `spec.md` §8. See `_event_bytes`."""
        return sum(_event_bytes(p.event) for p in self._queue)

    @property
    def unfinished_items(self) -> tuple[SseEvent, ...]:
        """Events of items that opened and never closed. **Every** ending drops these.

        `spec.md` §3 says why the alternative was impossible: a terminal proves the response ended, not that an item without a `done` became whole. Exposed rather than dropped here because *when* to drop is the ending's decision, not the assembler's.
        """
        return tuple(
            p.event for p in self._queue if isinstance(p.item, int) and p.item in self._open
        )

    @property
    def unattributed(self) -> tuple[SseEvent, ...]:
        """Events that belong to no item this proxy could identify. **Their disposal at an ending is not the same as `unfinished_items`'.**

        Where they go is `spec.md` §7.2's closing sequence to decide, and this property deliberately does not say what that answer is — an earlier version transcribed the rule into this docstring, the rule was then found wrong, and a copy in the code is one more place a correction has to reach. What is settled here, and independent of that answer, is that the two classes must be reported **apart**: an unclosed item is known to exist and known not to have finished, while these are not known to belong to any item at all — four of them in `openai==3.3.1` belong to none by construction, and one property returning both let the second inherit a disposal reason that does not apply to it.

        Held exactly like `unfinished_items` in the meantime, because releasing one while holding the other would reorder.
        """
        return tuple(p.event for p in self._queue if p.item is Attribution.UNATTRIBUTED)


def _item_of(event: SseEvent) -> int | Attribution:
    """Which output item an event belongs to, or why it belongs to none.

    Read off `output_index`, and **any event carrying one counts** — including event types this module has never heard of. That is the point: a `response.custom_tool_call_input.delta` is grouped correctly without anything here knowing what a custom tool call is.

    An event with no `output_index` is envelope only if `CONTROL_EVENTS` names it. Everything else is `UNATTRIBUTED`, which is a held position rather than a released one; `Attribution` records what is actually in that set.
    """
    if event.event in CONTROL_EVENTS:
        return Attribution.ENVELOPE
    payload: dict[str, Any] = event.json()
    index = payload.get("output_index")
    return index if isinstance(index, int) else Attribution.UNATTRIBUTED


@dataclass(slots=True)
class ResponsesPassthroughFramer:
    """Writes batches out. Holds no renumbering state, because there is nothing to renumber.

    Every counter the translating framer maintains — `sequence_number`, `output_index`, minted ids — exists to build events this proxy is inventing. Here it invents none, so it keeps none. `spec.md` §3 and §6.2 forbid rewriting any of them.

    It stays a class rather than collapsing into `RawEventBatch.encode` because `plan.md` gives this leg a framer of its own, in the position `ResponsesFramer` occupies for the translating leg. It carries no counter: what this leg observes is `spec.md` §10's business, and a bare tally with no consumer would be this slice deciding §10's carrier for it.
    """

    def batch(self, batch: RawEventBatch) -> bytes:
        return batch.encode()
