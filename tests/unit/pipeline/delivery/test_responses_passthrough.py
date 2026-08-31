"""The direct Responses passthrough assembler and framer.

Skeleton-level: grouping, ordering and byte fidelity. Replay, buffering policies, headers and cap accounting are later steps and are not exercised here — see `.dev/docs/direct-responses-passthrough/plan.md`.
"""

import orjson

from app.pipeline.delivery.formats.openai_responses_passthrough import (
    RawEventBatch,
    ResponsesPassthroughAssembler,
    ResponsesPassthroughFramer,
)
from app.pipeline.delivery.sse_source import SseEvent, parse_frame


def event(name: str, **payload: object) -> SseEvent:
    return SseEvent(event=name, data=orjson.dumps(payload).decode())


def drain(assembler: ResponsesPassthroughAssembler, events: list[SseEvent]) -> list[SseEvent]:
    """Every event the assembler released, flattened, in release order."""
    out: list[SseEvent] = []
    for one in events:
        for batch in assembler.push(one):
            out.extend(batch.events)
    return out


def test_an_item_type_nothing_here_knows_reaches_the_client_intact() -> None:
    """The case the whole topic exists for, and the one issue #2 was reported on.

    A `custom_tool_call` carries its input on `response.custom_tool_call_input.delta`, an event the translating assembler does not consume — which is why that path produced an empty block whose kind contradicted its payload, and tore the stream. Here nothing consumes it either, and that is precisely why it survives: grouping reads `output_index`, never the item's type, so an item this proxy has never heard of is carried without anything having to recognise it.

    Asserted on the released events being the input events, identically and in order. A weaker assertion — that *something* came out — would pass on an implementation that dropped the delta and kept the envelope.
    """
    sent = [
        event("response.output_item.added", output_index=0, item={"id": "ctc_1", "type": "custom_tool_call"}),
        event("response.custom_tool_call_input.delta", output_index=0, delta="ls "),
        event("response.custom_tool_call_input.delta", output_index=0, delta="-la"),
        event(
            "response.output_item.done",
            output_index=0,
            item={"id": "ctc_1", "type": "custom_tool_call", "name": "run_shell", "input": "ls -la"},
        ),
    ]

    assert drain(ResponsesPassthroughAssembler(), sent) == sent


def test_an_unknown_event_is_grouped_with_its_item_not_treated_as_envelope() -> None:
    """Grouping an unrecognised event by `output_index` is what makes the test above mean anything.

    **Measured 2026-08-31: the test above does not discriminate on its own.** Mutating `_item_of` to group only the three event names this module happens to name left all eight tests green — because in that scenario the delta, misfiled as a control event, had no earlier open item to be held behind, so it came out in the same position anyway. Same output, different reason.

    The difference is only observable while an item is open, so that is what this asserts. An event misfiled as envelope would not appear in `unfinished_items`, and §3 requires exactly those events to be dropped at an ending — so the mutation does not merely mis-order, it would leak a fragment of an unfinished item to the client.
    """
    assembler = ResponsesPassthroughAssembler()
    assembler.push(event("response.output_item.added", output_index=0, item={"type": "x"}))
    assembler.push(event("response.output_item.done", output_index=0, item={"type": "x"}))

    assembler.push(event("response.output_item.added", output_index=1, item={"type": "custom_tool_call"}))
    assembler.push(event("response.custom_tool_call_input.delta", output_index=1, delta="partial"))

    assert [e.event for e in assembler.unfinished_items] == [
        "response.output_item.added",
        "response.custom_tool_call_input.delta",
    ]


def test_nothing_is_released_before_its_item_closes() -> None:
    """Block-level delivery: the client sees a unit only once it is whole.

    The unit here is the output item, and its boundary is `output_item.done`. Until then the events are held — held, not dropped, which is the difference from the fallback that produced issue #2.
    """
    assembler = ResponsesPassthroughAssembler()

    assert assembler.push(event("response.output_item.added", output_index=0, item={"type": "x"})) == ()
    assert assembler.push(event("response.output_text.delta", output_index=0, delta="hi")) == ()

    released = assembler.push(event("response.output_item.done", output_index=0, item={"type": "x"}))

    assert len(released) == 1
    assert [e.event for e in released[0].events] == [
        "response.output_item.added",
        "response.output_text.delta",
        "response.output_item.done",
    ]


def test_a_finished_item_waits_behind_an_unfinished_earlier_one() -> None:
    """Interleaved lifecycles hold the queue rather than jumping it.

    Item 1 closes while item 0 is still open. Releasing 1 now would put it ahead of 0 on the wire, which is the one thing that makes `sequence_number` run backwards and `output_index` disagree with the client's snapshot. `spec.md` §4 accepts head-of-line blocking instead, so nothing moves until 0 closes — and then both go out in their original order.

    The three Responses-stream cassettes in this repository never interleave, so this is designed against the protocol rather than against a sample; that is recorded in the Spec as a trend sample, not a guarantee.
    """
    assembler = ResponsesPassthroughAssembler()
    assembler.push(event("response.output_item.added", output_index=0, item={"type": "a"}))
    assembler.push(event("response.output_item.added", output_index=1, item={"type": "b"}))

    assert assembler.push(event("response.output_item.done", output_index=1, item={"type": "b"})) == ()

    released = assembler.push(event("response.output_item.done", output_index=0, item={"type": "a"}))

    assert len(released) == 1
    assert [(e.event, e.json()["output_index"]) for e in released[0].events] == [
        ("response.output_item.added", 0),
        ("response.output_item.added", 1),
        ("response.output_item.done", 1),
        ("response.output_item.done", 0),
    ]


def test_an_items_events_do_not_straddle_a_release_boundary() -> None:
    """The other interleaving, and the one no test covered: an earlier item closes *late*.

    `test_a_finished_item_waits_behind_an_unfinished_earlier_one` walks the case where the later item closes first. Reverse it — item 0 closes while item 1 is still open — and stopping at the first blocked event releases `[added(0)]` on its own, with `done(0)` left queued behind item 1's entire lifecycle.

    §4 rules that "already `done`" means the item's `done` falls inside the prefix, so nothing goes. Two things go wrong otherwise, and the second is the expensive one: the client gets half a group, and the attempt is committed by a byte carrying no content — which shuts §5's whole-attempt replay window for a turn that could still have been replayed intact, had item 1 failed retryably a moment later.
    """
    assembler = ResponsesPassthroughAssembler()
    # A control-only prefix is a delivery unit, and §5 forbids delivering it on its own — it rides out with the first batch of item events. The assembler releases it to its caller here; whether it reaches the client is the delivery step's decision, not this one's.
    assert assembler.push(event("response.created", response={"id": "resp_1"})) != ()

    assembler.push(event("response.output_item.added", output_index=0, item={"type": "a"}))
    assembler.push(event("response.output_item.added", output_index=1, item={"type": "b"}))
    assembler.push(event("response.output_text.delta", output_index=1, delta="hi"))

    assert assembler.push(event("response.output_item.done", output_index=0, item={"type": "a"})) == ()


def test_retreating_past_one_straddling_item_can_expose_another() -> None:
    """One pass is not enough, because each retreat lengthens the tail it is checked against.

    Here item 0 and item 1 both complete before item 2 opens, but their events interleave and item 1's `done` lands after item 2's `added`. Retreating past item 1 puts item 0's `done` into the tail, so item 0 straddles a boundary that was fine an instant earlier. A single-pass implementation releases item 0's `added` alone — exactly the split the rule exists to prevent.
    """
    assembler = ResponsesPassthroughAssembler()
    assembler.push(event("response.output_item.added", output_index=0, item={"type": "a"}))
    assembler.push(event("response.output_item.added", output_index=1, item={"type": "b"}))
    assembler.push(event("response.output_item.done", output_index=0, item={"type": "a"}))
    assembler.push(event("response.output_item.added", output_index=2, item={"type": "c"}))

    assert assembler.push(event("response.output_item.done", output_index=1, item={"type": "b"})) == ()


def test_control_events_keep_their_place_in_the_queue() -> None:
    """`response.created` belongs to no item, and must not overtake one either.

    It is released with the prefix it sits in, which is what keeps the client's view of the envelope in the order upstream wrote it. When it may be *submitted* is a separate question that `spec.md` §5 answers, and the skeleton does not decide it.
    """
    assembler = ResponsesPassthroughAssembler()

    assert assembler.push(event("response.created", response={"id": "resp_1"})) != ()

    assembler.push(event("response.output_item.added", output_index=0, item={"type": "x"}))
    held = assembler.push(event("response.completed", response={"id": "resp_1"}))

    # The terminal is queued behind the open item rather than delivered ahead of it.
    assert held == ()
    assert [e.event for e in assembler.unfinished_items] == ["response.output_item.added"]


def test_an_unfinished_tail_is_visible_to_whoever_ends_the_stream() -> None:
    """The assembler exposes the tail; it does not decide when to drop it.

    `spec.md` §3 drops an unclosed item's events at every ending, and §7.2 says which ending. Both are the caller's business — an assembler that dropped them itself would be making an ending decision from inside the parser.
    """
    assembler = ResponsesPassthroughAssembler()
    assembler.push(event("response.output_item.added", output_index=0, item={"type": "x"}))
    assembler.push(event("response.output_item.done", output_index=0, item={"type": "x"}))
    assembler.push(event("response.output_item.added", output_index=1, item={"type": "y"}))
    assembler.push(event("response.output_text.delta", output_index=1, delta="partial"))

    assert [e.event for e in assembler.unfinished_items] == [
        "response.output_item.added",
        "response.output_text.delta",
    ]


def test_a_done_for_an_item_that_never_opened_still_closes_it() -> None:
    """Defensive, and the docstring used to overstate why.

    Treating an orphan `done` as an item still open would wedge the queue forever: nothing can be released past an item that will never close. Tolerating it costs nothing, so it is closed and its events go out.

    It used to say "upstream is on record for" this shape. It is not. `hosted-web-search-spec.md` §12 lists it as open question P7 — *"是否真的存在「`done` 无 `added`」形态"* — and records that both of this project's measurements carried an `added`; the three Responses-stream cassettes pair every `added` with its `done`. What is on record is the **reference project's** own implementation dropping such an item silently, which is a different fact about a different program. Leaving the claim would have closed P7 with an observation that never happened.
    """
    assembler = ResponsesPassthroughAssembler()

    released = assembler.push(event("response.output_item.done", output_index=0, item={"type": "x"}))

    assert len(released) == 1
    assert assembler.unfinished_items == ()


def test_an_event_that_cannot_be_attributed_is_held_rather_than_released() -> None:
    """§4: an event that cannot be attributed to an item is held conservatively until the terminal.

    The shape is real rather than hypothetical. Of the 58 members of `ResponseStreamEvent` in `openai==3.3.1`, eleven carry no `output_index`; seven are the envelope and the other four are the audio series, which carry model output with neither an `output_index` nor an `item_id`. A payload that fails to parse lands in the same place, since `SseEvent.json()` answers `{}`.

    The earlier implementation returned a bare `None` for both "envelope" and "cannot attribute", so this event was released immediately as though it were envelope — a fragment of something that may never close, delivered to the client. Asserted before any item opens, which is where the old code released it outright.
    """
    assembler = ResponsesPassthroughAssembler()

    assert assembler.push(event("response.audio.delta", delta="...")) == ()
    assert [e.event for e in assembler.unattributed] == ["response.audio.delta"]
    assert assembler.unfinished_items == ()


def test_an_unattributable_event_blocks_the_prefix_behind_it() -> None:
    """Holding it while releasing what follows would be a reorder, which §4 refuses.

    So it is a barrier, not a skip: a whole item that closes after it still waits. That is the same head-of-line trade §4 already accepts for an open item, applied to an event whose owner is unknown.
    """
    assembler = ResponsesPassthroughAssembler()
    assembler.push(event("response.audio.delta", delta="..."))

    assembler.push(event("response.output_item.added", output_index=0, item={"type": "x"}))

    assert assembler.push(event("response.output_item.done", output_index=0, item={"type": "x"})) == ()


def test_an_unattributable_event_is_reported_apart_from_an_unclosed_tail() -> None:
    """The two are held alike and disposed of differently, so the assembler reports them apart.

    Held alike: both block the prefix, because releasing one while holding the other would reorder. Disposed of differently: `spec.md` §7.2 drops an unclosed item's tail at **every** ending, while an unattributable event's fate depends on a separate predicate. **What that predicate is has already changed once** — v8 keyed it on the ending's source, v9 keys it on whether any item is unclosed at close time — so this test pins only the part that survived both: the two classes come out of the assembler apart. Collapsing them into one property is what let the second inherit the first's disposal reason, and that reason, "the proxy cannot tell whose it is", is the one §2.1 rejects.

    Asserted with an item open around the unattributable event, so the two sets are non-empty at the same time and an implementation that returned one for both would fail.
    """
    assembler = ResponsesPassthroughAssembler()
    assembler.push(event("response.output_item.added", output_index=0, item={"type": "x"}))
    assembler.push(event("response.output_text.delta", delta="no output_index at all"))
    assembler.push(event("response.output_text.delta", output_index=0, delta="hi"))

    assert [e.event for e in assembler.unfinished_items] == [
        "response.output_item.added",
        "response.output_text.delta",
    ]
    assert [e.data for e in assembler.unattributed] == ['{"delta":"no output_index at all"}']


def test_queued_is_envelope_and_travels_with_its_prefix() -> None:
    """`response.queued` is in the SDK union and was missing from `CONTROL_EVENTS`.

    Harmless while the two non-item answers shared one slot; once they are told apart it decides which, so an omission would hold the envelope frame — and everything after it — to the terminal.
    """
    assembler = ResponsesPassthroughAssembler()

    assert assembler.push(event("response.queued", response={"id": "resp_1"})) != ()
    assert assembler.unfinished_items == ()
    assert assembler.unattributed == ()


def test_a_second_attempt_needs_a_second_assembler() -> None:
    """`_closed` is permanent, so reuse across attempts silently stops holding anything.

    Not a supported mode — §5 discards the old attempt's queue wholesale on replay, so an attempt gets its own assembler. Asserted because the failure is silent: feeding attempt 2 to a used instance produces no error and no observable fact, just per-event forwarding where block-level delivery should be. This test pins the lifetime the class requires rather than a behaviour it offers.
    """
    used = ResponsesPassthroughAssembler()
    used.push(event("response.output_item.added", output_index=0, item={"type": "x"}))
    used.push(event("response.output_item.done", output_index=0, item={"type": "x"}))

    # Attempt 2 through the same instance: index 0 is already closed, so nothing is ever held.
    assert used.push(event("response.output_item.added", output_index=0, item={"type": "x"})) != ()

    fresh = ResponsesPassthroughAssembler()
    assert fresh.push(event("response.output_item.added", output_index=0, item={"type": "x"})) == ()


def test_the_framer_writes_the_payload_it_was_given() -> None:
    """No renumbering, no re-serialising, and multi-line payloads survive.

    Every counter the translating framer keeps exists to build events this proxy invents; this one invents none. The multi-line case is in here because it is exactly what `_report_failure` used to lose — one `data:` line followed by a bare line, which a reader skips.
    """
    batch = RawEventBatch(
        events=(
            SseEvent(event="response.output_text.delta", data='{"output_index":0,"delta":"a"}'),
            SseEvent(event="x.unknown", data="first\nsecond"),
        )
    )

    wire = ResponsesPassthroughFramer().batch(batch)
    frames = [parse_frame(f) for f in wire.split(b"\n\n") if f.strip()]

    assert [(f.event, f.data) for f in frames if f is not None] == [
        ("response.output_text.delta", '{"output_index":0,"delta":"a"}'),
        ("x.unknown", "first\nsecond"),
    ]


def test_held_bytes_measures_the_text_actually_held() -> None:
    """The cap in `spec.md` §8 bounds what this proxy is holding, per the user's own config wording.

    Measured on the raw event text, because that is what is in the queue — not `repr` of a parsed payload, which is what the Anthropic-side block measures and would be a different number for the same bytes.
    """
    assembler = ResponsesPassthroughAssembler()
    assert assembler.held_bytes == 0

    assembler.push(event("response.output_item.added", output_index=0, item={"type": "x"}))
    held = assembler.held_bytes

    assert held > 0
    assembler.push(event("response.output_item.done", output_index=0, item={"type": "x"}))
    # Released, so no longer held.
    assert assembler.held_bytes == 0
