"""The direct Responses passthrough assembler and framer.

Skeleton-level: grouping, ordering and byte fidelity. Replay, buffering policies, headers and cap accounting are later steps and are not exercised here — see `.dev/docs/direct-passthrough/plan.md`.
"""

from typing import Any

import orjson
import pytest

from app.errors import ErrorCategory, ErrorInfo
from app.pipeline.delivery.assembling import Terminal
from app.pipeline.delivery.blocks import BlockBuffer, BufferCapExceeded
from app.pipeline.delivery.formats.openai_responses import ResponsesFramer
from app.pipeline.delivery.formats.openai_responses_passthrough import (
    RESPONSES_DIALECT,
    requires_client_action,
    responses_passthrough_assembler,
    stabilise_stream_ids,
)
from app.pipeline.delivery.passthrough import PassthroughAssembler, PassthroughFramer, RawEventBatch
from app.pipeline.delivery.sse_source import SseEvent, parse_frame


def event(name: str, **payload: object) -> SseEvent:
    return SseEvent(event=name, data=orjson.dumps(payload).decode())


def drain(assembler: PassthroughAssembler, events: list[SseEvent]) -> list[SseEvent]:
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

    assert drain(responses_passthrough_assembler(), sent) == sent


def test_an_unknown_event_is_grouped_with_its_item_not_treated_as_envelope() -> None:
    """Grouping an unrecognised event by `output_index` is what makes the test above mean anything.

    **Measured 2026-08-31: the test above does not discriminate on its own.** Mutating `_item_of` to group only the three event names this module happens to name left all eight tests green — because in that scenario the delta, misfiled as a control event, had no earlier open item to be held behind, so it came out in the same position anyway. Same output, different reason.

    The difference is only observable while an item is open, so that is what this asserts. An event misfiled as envelope would not appear in `unfinished_items`, and §3 requires exactly those events to be dropped at an ending — so the mutation does not merely mis-order, it would leak a fragment of an unfinished item to the client.
    """
    assembler = responses_passthrough_assembler()
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
    assembler = responses_passthrough_assembler()

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
    assembler = responses_passthrough_assembler()
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
    assembler = responses_passthrough_assembler()
    # Held, not released: §4 says a control-only prefix rides out with the first batch of item events, because delivering it alone would put upstream's first native event in front of the client and §5 counts that as committing the attempt.
    assert assembler.push(event("response.created", response={"id": "resp_1"})) == ()

    assembler.push(event("response.output_item.added", output_index=0, item={"type": "a"}))
    assembler.push(event("response.output_item.added", output_index=1, item={"type": "b"}))
    assembler.push(event("response.output_text.delta", output_index=1, delta="hi"))

    assert assembler.push(event("response.output_item.done", output_index=0, item={"type": "a"})) == ()


def test_retreating_past_one_straddling_item_can_expose_another() -> None:
    """One pass is not enough, because each retreat lengthens the tail it is checked against.

    Here item 0 and item 1 both complete before item 2 opens, but their events interleave and item 1's `done` lands after item 2's `added`. Retreating past item 1 puts item 0's `done` into the tail, so item 0 straddles a boundary that was fine an instant earlier. A single-pass implementation releases item 0's `added` alone — exactly the split the rule exists to prevent.
    """
    assembler = responses_passthrough_assembler()
    assembler.push(event("response.output_item.added", output_index=0, item={"type": "a"}))
    assembler.push(event("response.output_item.added", output_index=1, item={"type": "b"}))
    assembler.push(event("response.output_item.done", output_index=0, item={"type": "a"}))
    assembler.push(event("response.output_item.added", output_index=2, item={"type": "c"}))

    assert assembler.push(event("response.output_item.done", output_index=1, item={"type": "b"})) == ()


def test_control_events_keep_their_place_in_the_queue() -> None:
    """`response.created` belongs to no item, and must not overtake one either.

    It is released with the prefix it sits in, which is what keeps the client's view of the envelope in the order upstream wrote it. When it may be *submitted* is a separate question that `spec.md` §5 answers, and the skeleton does not decide it.
    """
    assembler = responses_passthrough_assembler()

    assert assembler.push(event("response.created", response={"id": "resp_1"})) == ()

    assembler.push(event("response.output_item.added", output_index=0, item={"type": "x"}))
    held = assembler.push(event("response.completed", response={"id": "resp_1"}))

    # The terminal is queued behind the open item rather than delivered ahead of it.
    assert held == ()
    assert [e.event for e in assembler.unfinished_items] == ["response.output_item.added"]

    # It closes, and now everything goes out together in the order upstream wrote it — the envelope frames included.
    released = assembler.push(event("response.output_item.done", output_index=0, item={"type": "x"}))
    assert len(released) == 1
    assert [e.event for e in released[0].events] == [
        "response.created",
        "response.output_item.added",
        "response.completed",
        "response.output_item.done",
    ]


def test_an_unfinished_tail_is_visible_to_whoever_ends_the_stream() -> None:
    """The assembler exposes the tail; it does not decide when to drop it.

    `spec.md` §3 drops an unclosed item's events at every ending, and §7.2 says which ending. Both are the caller's business — an assembler that dropped them itself would be making an ending decision from inside the parser.
    """
    assembler = responses_passthrough_assembler()
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
    assembler = responses_passthrough_assembler()

    released = assembler.push(event("response.output_item.done", output_index=0, item={"type": "x"}))

    assert len(released) == 1
    assert assembler.unfinished_items == ()


def test_an_event_that_cannot_be_attributed_is_held_rather_than_released() -> None:
    """§4: an event that cannot be attributed to an item is held conservatively until the terminal.

    The shape is real rather than hypothetical. Of the 58 members of `ResponseStreamEvent` in `openai==3.3.1`, eleven carry no `output_index`; seven are the envelope and the other four are the audio series, which carry model output with neither an `output_index` nor an `item_id`. A payload that fails to parse lands in the same place, since `SseEvent.json()` answers `{}`.

    The earlier implementation returned a bare `None` for both "envelope" and "cannot attribute", so this event was released immediately as though it were envelope — a fragment of something that may never close, delivered to the client. Asserted before any item opens, which is where the old code released it outright.
    """
    assembler = responses_passthrough_assembler()

    assert assembler.push(event("response.audio.delta", delta="...")) == ()
    assert [e.event for e in assembler.unattributed] == ["response.audio.delta"]
    assert assembler.unfinished_items == ()


def test_an_unattributable_event_blocks_the_prefix_behind_it() -> None:
    """Holding it while releasing what follows would be a reorder, which §4 refuses.

    So it is a barrier, not a skip: a whole item that closes after it still waits. That is the same head-of-line trade §4 already accepts for an open item, applied to an event whose owner is unknown.
    """
    assembler = responses_passthrough_assembler()
    assembler.push(event("response.audio.delta", delta="..."))

    assembler.push(event("response.output_item.added", output_index=0, item={"type": "x"}))

    assert assembler.push(event("response.output_item.done", output_index=0, item={"type": "x"})) == ()


def test_an_unattributable_event_is_reported_apart_from_an_unclosed_tail() -> None:
    """The two are held alike and disposed of differently, so the assembler reports them apart.

    Held alike: both block the prefix, because releasing one while holding the other would reorder. Disposed of differently: `spec.md` §7.2 drops an unclosed item's tail at **every** ending, while an unattributable event's fate depends on a separate predicate. **What that predicate is has already changed once** — v8 keyed it on the ending's source, v9 keys it on whether any item is unclosed at close time — so this test pins only the part that survived both: the two classes come out of the assembler apart. Collapsing them into one property is what let the second inherit the first's disposal reason, and that reason, "the proxy cannot tell whose it is", is the one §2.1 rejects.

    Asserted with an item open around the unattributable event, so the two sets are non-empty at the same time and an implementation that returned one for both would fail.
    """
    assembler = responses_passthrough_assembler()
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
    assembler = responses_passthrough_assembler()

    # Envelope, so it is held neither as an unclosed item's fragment nor as an unattributable one — but §4 still does not deliver a control-only prefix on its own, so nothing comes out until content does.
    assert assembler.push(event("response.queued", response={"id": "resp_1"})) == ()
    assert assembler.unfinished_items == ()
    assert assembler.unattributed == ()

    # Had it been judged unattributable instead, it would have been held to the terminal and blocked everything behind it. It is not.
    released = assembler.push(event("response.output_item.done", output_index=0, item={"type": "x"}))
    assert len(released) == 1
    assert [e.event for e in released[0].events] == ["response.queued", "response.output_item.done"]


def test_a_second_attempt_needs_a_second_assembler() -> None:
    """`_closed` is permanent, so reuse across attempts silently stops holding anything.

    Not a supported mode — §5 discards the old attempt's queue wholesale on replay, so an attempt gets its own assembler. Asserted because the failure is silent: feeding attempt 2 to a used instance produces no error and no observable fact, just per-event forwarding where block-level delivery should be. This test pins the lifetime the class requires rather than a behaviour it offers.
    """
    used = responses_passthrough_assembler()
    used.push(event("response.output_item.added", output_index=0, item={"type": "x"}))
    used.push(event("response.output_item.done", output_index=0, item={"type": "x"}))

    # Attempt 2 through the same instance: index 0 is already closed, so nothing is ever held.
    assert used.push(event("response.output_item.added", output_index=0, item={"type": "x"})) != ()

    fresh = responses_passthrough_assembler()
    assert fresh.push(event("response.output_item.added", output_index=0, item={"type": "x"})) == ()


def test_the_framer_writes_the_payload_it_was_given() -> None:
    """No renumbering, no re-serialising, and multi-line payloads survive.

    Every counter the translating framer keeps exists to build events this proxy invents; this one invents none. The multi-line case is in here because it is exactly what `_report_failure` used to lose — one `data:` line followed by a bare line, which a reader skips.
    """
    batch = RawEventBatch(
        events=(
            SseEvent(event="response.output_text.delta", data='{"output_index":0,"delta":"a"}'),
            SseEvent(event="x.unknown", data="first\nsecond"),
        ),
        dialect=RESPONSES_DIALECT,
    )

    framer = PassthroughFramer(delegate=ResponsesFramer(response_id="resp_1", model="m"))
    wire = b"".join(framer.block(batch))
    frames = [parse_frame(f) for f in wire.split(b"\n\n") if f.strip()]

    assert [(f.event, f.data) for f in frames if f is not None] == [
        ("response.output_text.delta", '{"output_index":0,"delta":"a"}'),
        ("x.unknown", "first\nsecond"),
    ]


def test_queued_bytes_measures_the_text_actually_held() -> None:
    """The cap in `spec.md` §8 bounds what this proxy is holding, per the user's own config wording.

    Measured on the raw event text, because that is what is in the queue — not `repr` of a parsed payload, which is what the Anthropic-side block measures and would be a different number for the same bytes.
    """
    assembler = responses_passthrough_assembler()
    assert assembler.queued_bytes == 0

    assembler.push(event("response.output_item.added", output_index=0, item={"type": "x"}))
    held = assembler.queued_bytes

    assert held > 0
    assembler.push(event("response.output_item.done", output_index=0, item={"type": "x"}))
    # Released, so no longer held.
    assert assembler.queued_bytes == 0


def test_the_same_type_answers_oppositely_by_its_own_execution_field() -> None:
    """§7.1's whole reason for reading the item rather than a type table.

    `ResponseToolSearchCall` declares `execution: Literal["server", "client"]`, so a table keyed on `tool_search_call` alone would be wrong for one of the two halves whichever answer it picked. Asserted as a pair, because either one alone passes on a constant.
    """
    assert requires_client_action({"type": "tool_search_call", "execution": "client"}) is True
    assert requires_client_action({"type": "tool_search_call", "execution": "server"}) is False


def test_an_item_type_nothing_here_knows_is_assumed_to_need_the_client() -> None:
    """The conservative direction, and §2.1 is why it is that one.

    Answering `False` for an unknown type would hold whatever the client has to act on until the terminal, which makes the set of types this proxy recognises the ceiling on what a client can do. Releasing early costs one extra flush; withholding costs the turn. An item with no readable `type` gets the same answer for the same reason.
    """
    assert requires_client_action({"type": "some_2027_tool_call"}) is True
    assert requires_client_action({}) is True


def test_a_hosted_tool_the_upstream_runs_itself_needs_nothing_from_the_client() -> None:
    """The control for the test above: if everything answered `True`, `until-tool-use` would release on the first item and mean nothing."""
    assert requires_client_action({"type": "web_search_call"}) is False
    assert requires_client_action({"type": "message"}) is False


def test_a_batch_answers_from_whichever_event_carries_the_item() -> None:
    """Not from the closing event, because the two dialects put the item in different places.

    A Responses `output_item.done` carries the finished item; an Anthropic `content_block_stop` carries only an index, and the block's type arrived on `content_block_start`. A predicate that asked only the closing event would answer `False` for every Anthropic tool call. Scanning the batch is safe because §4 already guarantees an item's events never straddle a release boundary — if the item is in here, its whole group is.

    Asserted as a pair on `tool_search_call`, the type whose answer is decided by a field spread across the group: the opening event announces the type and the closing one carries `execution`.
    """
    def group(execution: str) -> RawEventBatch:
        return RawEventBatch(
            events=(
                SseEvent(
                    event="response.output_item.added",
                    data='{"output_index":0,"item":{"type":"tool_search_call"}}',
                ),
                SseEvent(
                    event="response.output_item.done",
                    data='{"output_index":0,"item":{"type":"tool_search_call","execution":"'
                    + execution
                    + '"}}',
                ),
            ),
            dialect=RESPONSES_DIALECT,
        )

    assert group("client").requires_client_action is True
    assert group("server").requires_client_action is False


def test_a_terminal_lifts_the_hold_on_a_response_with_no_items() -> None:
    """§5's fourth row: an item-less terminal is submitted with this attempt's control events.

    Without this the hold rule would be a deadlock for the shortest legal response there is — `created` then `completed`, nothing in between. Holding for "the first batch of item events" that never comes would deliver the client nothing at all.
    """
    assembler = responses_passthrough_assembler()

    assert assembler.push(event("response.created", response={"id": "resp_1"})) == ()

    released = assembler.push(event("response.completed", response={"id": "resp_1"}))

    assert len(released) == 1
    assert [e.event for e in released[0].events] == ["response.created", "response.completed"]


def test_the_terminal_facts_are_recorded_without_touching_the_wire() -> None:
    """§10 wants the authoritative status and usage; §6.3 forbids deriving anything back onto the events.

    So the assembler reads upstream's terminal for the side record and still carries that same event out verbatim inside a batch. Both halves are asserted here, because keeping only the first is how a leg ends up reporting facts it also quietly rewrote.

    `upstream_usage` is upstream's own object rather than the Anthropic conversion beside it: that conversion subtracts the cached input and drops reasoning tokens, and a leg reporting what upstream said needs the original.
    """
    assembler = responses_passthrough_assembler()
    assert assembler.terminal.seen is False

    assembler.push(event("response.output_item.added", output_index=0, item={"type": "message"}))
    assembler.push(
        event("response.output_item.done", output_index=0, item={"type": "message"})
    )
    released = assembler.push(
        event(
            "response.completed",
            response={"id": "resp_1", "status": "completed", "usage": {"input_tokens": 7}},
        )
    )

    assert assembler.terminal.seen is True
    assert assembler.terminal.stop_reason == "end_turn"
    assert assembler.terminal.upstream_usage == {"input_tokens": 7}
    # And the same event still goes to the client as upstream wrote it.
    assert [e.event for e in released[0].events][-1] == "response.completed"


def test_a_turn_that_asked_the_client_to_act_says_so_in_its_stop_reason() -> None:
    """The control for the test above — otherwise `end_turn` would be a constant.

    The two legs establish this differently and mean the same thing: the translating assembler knows it built a tool-use block, this one knows an item required client action (§7.1). Both feed the same shared reader.
    """
    assembler = responses_passthrough_assembler()
    assembler.push(event("response.output_item.added", output_index=0, item={"type": "function_call"}))
    assembler.push(
        event("response.output_item.done", output_index=0, item={"type": "function_call", "name": "f"})
    )
    assembler.push(event("response.completed", response={"id": "resp_1"}))

    assert assembler.terminal.stop_reason == "tool_use"


def test_an_upstream_failure_is_carried_with_its_own_name_and_payload() -> None:
    """What makes verbatim replay possible at all: `_report_failure` writes `event` and `raw_data` back out.

    So the record has to keep upstream's own event name rather than normalising to `error` — `response.failed` and `response.cancelled` are different things to a client of that API — and the payload as text rather than a re-serialised dict, because a round trip through an encoder keeps the fields and not the bytes.
    """
    assembler = responses_passthrough_assembler()
    raw = '{"response":{"id":"resp_1","error":{"code":"server_error","message":"boom"}}}'

    assembler.push(SseEvent(event="response.failed", data=raw))

    failure = assembler.failure
    assert failure is not None
    assert failure.event == "response.failed"
    assert failure.raw_data == raw
    assert failure.info.code == "server_error"


def test_cut_mid_block_is_true_only_while_an_item_is_open() -> None:
    """It tells a stream cut *through* an item from one cut *between* items, and the two endings differ.

    A clean close between items delivers everything whole and needs no error frame; a close through one does. Both leave `terminal.seen` false, so this is the only observable that separates them.
    """
    assembler = responses_passthrough_assembler()
    assert assembler.cut_mid_block is False

    assembler.push(event("response.output_item.added", output_index=0, item={"type": "message"}))
    assert assembler.cut_mid_block is True

    assembler.push(event("response.output_item.done", output_index=0, item={"type": "message"}))
    assert assembler.cut_mid_block is False


def test_the_framer_invents_no_envelope_and_no_terminal() -> None:
    """Two empties that are not the same empty, and neither is an oversight.

    Upstream's own opening event and its own terminal arrive as ordinary events and ride out inside batches. Emitting counterparts here would deliver each of them twice, with a different id the second time — the invented one is not upstream's.
    """
    framer = PassthroughFramer(delegate=ResponsesFramer(response_id="resp_1", model="m"))

    assert framer.preamble() == ()
    assert framer.terminal(Terminal(seen=True, stop_reason="end_turn")) == ()


def test_the_framer_refuses_to_synthesise_a_terminal() -> None:
    """§8 forbids this leg inventing a successful terminal, and `stream._deliver` reads this to know.

    On a translating leg an upstream that closes cleanly between items gets the configured stop reason written for it, and the turn reads as complete. §5.1 requires an error there instead: the only honest terminal is upstream's, and it never arrived.
    """
    framer = PassthroughFramer(delegate=ResponsesFramer(response_id="resp_1", model="m"))

    assert framer.synthesises_terminal is False


def test_the_framer_delegates_the_two_frames_this_leg_still_invents() -> None:
    """An error frame and a keep-alive really are this side's own, and each dialect already spells them.

    Delegating rather than reimplementing is what keeps one spelling: a second copy here would drift from `error-envelope/spec.md` §6.3 the first time that shape changed. Asserted against the leg's ordinary framer producing the identical bytes.
    """
    delegate = ResponsesFramer(response_id="resp_1", model="m")
    framer = PassthroughFramer(delegate=delegate)
    info = ErrorInfo(
        category=ErrorCategory.UPSTREAM, message="boom", status_code=502, code="upstream_stream_failed"
    )

    assert framer.keepalive() == delegate.keepalive()
    assert framer.error(info) == ResponsesFramer(response_id="resp_1", model="m").error(info)


def test_the_opening_envelope_event_does_not_claim_upstream_finished() -> None:
    """The blocker an independent review found, and the assertion that would have caught it.

    The shared terminal reader used to set `seen = True` on its first line, with the guard living outside it in the translating assembler's `kind in {...}` branch. The passthrough then called it for *every* envelope event, so `response.created` — upstream's very first frame — reported that upstream had finished, with a `stop_reason` of `end_turn` nobody had said.

    Everything downstream that asks "did upstream finish" then answered yes. Measured across three endings: a torn stream left the delivery loop as an orderly ending with no error frame, the exception swallowed and replay never even asked; a clean EOF without a terminal wrote nothing; the completion line logged `ok`. The leg was silently succeeding at every way of failing.

    The existing terminal test asserts `seen is False` too, but before pushing anything and without ever sending `response.created`, so it had no discriminating power here at all.
    """
    assembler = responses_passthrough_assembler()

    assembler.push(event("response.created", response={"id": "resp_1"}))

    assert assembler.terminal.seen is False
    assert assembler.terminal.stop_reason == ""

    assembler.push(event("response.in_progress", response={"id": "resp_1"}))

    assert assembler.terminal.seen is False


def test_an_upstream_failure_event_goes_out_once() -> None:
    """It is both an envelope event and a failure, and each half had its own delivery path.

    The batch carried it because it is envelope; `stream._report_failure` replayed it verbatim because it is a failure. The client received upstream's `response.failed` twice, byte-identically — a behaviour this leg introduced, since the translating leg only ever produced the one frame.

    It stays in the queue regardless of who emits it, because §5's fourth row uses a terminal to lift the hold on a control-only prefix. Asserted on both halves: the hold is lifted (something comes out) and the failure itself is not in what comes out.
    """
    assembler = responses_passthrough_assembler()
    delivered = [
        e.event
        for e in drain(
            assembler,
            [
                event("response.created", response={"id": "resp_1"}),
                event("response.output_item.added", output_index=0, item={"type": "message"}),
                event("response.output_item.done", output_index=0, item={"type": "message"}),
                SseEvent(
                    event="response.failed",
                    data='{"response":{"error":{"code":"server_error"}}}',
                ),
            ],
        )
    ]

    assert assembler.failure is not None
    assert delivered == [
        "response.created",
        "response.output_item.added",
        "response.output_item.done",
    ]
    assert "response.failed" not in delivered


def test_an_item_that_never_closes_does_not_take_the_whole_response_with_it() -> None:
    """§7.2's closing sequence, and what its absence cost.

    An item that opens and never closes blocks everything behind it — that is head-of-line blocking working as §4 intends, while the stream is live. At the ending it must stop: the groups queued behind that item are *finished*, not half-built, and upstream's own terminal is queued there too. Without a closing sequence they were all abandoned, so one unclosed item produced a 200 with zero bytes.

    Step 1 still drops the unclosed item's own events. Step 3 drops the unattributable ones too, because with an item open one of them may be its missing half.
    """
    assembler = responses_passthrough_assembler()
    assembler.push(event("response.created", response={"id": "resp_1"}))
    assembler.push(event("response.output_item.added", output_index=0, item={"type": "a"}))
    assembler.push(event("response.output_text.delta", output_index=0, delta="never closes"))
    assembler.push(event("response.output_item.added", output_index=1, item={"type": "b"}))
    assembler.push(event("response.output_item.done", output_index=1, item={"type": "b"}))
    assembler.push(event("response.completed", response={"id": "resp_1"}))

    closing = assembler.close()

    assert len(closing) == 1
    assert [e.event for e in closing[0].events] == [
        "response.created",
        # item 0's two events are dropped — it never closed.
        "response.output_item.added",
        "response.output_item.done",
        "response.completed",
    ]
    assert [e.json().get("output_index") for e in closing[0].events if "output_index" in e.json()] == [1, 1]


def test_the_closing_sequence_keeps_an_unattributable_event_when_nothing_is_open() -> None:
    """The other half of step 3, and the control for the test above.

    With no item unclosed, an unattributable event cannot be some open item's missing half, so dropping it would be refusing a protocol-legal event because this proxy could not tell whose it was — the reason §2.1 rejects.
    """
    assembler = responses_passthrough_assembler()
    assembler.push(event("response.created", response={"id": "resp_1"}))
    assembler.push(event("response.audio.delta", delta="..."))

    closing = assembler.close()

    assert len(closing) == 1
    assert [e.event for e in closing[0].events] == ["response.created", "response.audio.delta"]


def test_the_cap_can_see_what_the_assembler_is_holding() -> None:
    """§8 counts the queue first, and it was outside the buffer's view entirely.

    `BlockBuffer` only ever measured units that had already been released to it. On this leg an item that opens and never closes keeps every later group queued in the assembler, so `buffer_cap_bytes` — 16MiB by default, and enabled by default — bounded nothing at all there.
    """
    assembler = responses_passthrough_assembler()
    buffer: BlockBuffer[RawEventBatch] = BlockBuffer(policy="block", cap_bytes=200)

    assembler.push(event("response.output_item.added", output_index=0, item={"type": "a"}))
    for _ in range(20):
        assembler.push(event("response.output_text.delta", output_index=0, delta="x" * 40))

    assert assembler.queued_bytes > 200
    with pytest.raises(BufferCapExceeded):
        buffer.enforce_cap_over(assembler.queued_bytes)


def stabilised(events: list[SseEvent]) -> list[dict[str, Any]]:
    return [orjson.loads(e.data) for e in stabilise_stream_ids(tuple(events))]


def drifting_item(index: int, item_id: str, *, seal: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"type": "reasoning", "id": item_id, "summary": []}
    if seal is not None:
        item["encrypted_content"] = seal
    return {"output_index": index, "item": item}


def test_every_event_of_an_item_takes_the_id_its_closing_event_carried() -> None:
    """`spec.md` §6.6. Copilot spells the same item differently on every event it appears in.

    Measured 2026-09-02 over one real stream: ten distinct ids for a single `output_index`, and three distinct `response.id` values across the envelope. Codex renders such a stream's answer more than once, which is what this reshape exists to stop — while the leg without it forwards exactly what upstream sent, which is what `spec.md` §6.2 requires of anything called native.

    Asserted on the *closing* id specifically, not merely on "all the same": stabilising onto the opening id would satisfy a same-ness assertion and is the one direction that breaks a seal.
    """
    events = [
        SseEvent("response.output_item.added", orjson.dumps(drifting_item(0, "opened")).decode()),
        SseEvent("response.output_text.delta", orjson.dumps({"output_index": 0, "item_id": "middle", "delta": "hi"}).decode()),
        SseEvent("response.output_item.done", orjson.dumps(drifting_item(0, "closed")).decode()),
    ]

    added, delta, done = stabilised(events)

    assert added["item"]["id"] == "closed"
    assert delta["item_id"] == "closed"
    assert done["item"]["id"] == "closed"


def test_the_closing_event_is_not_touched_at_all() -> None:
    """It carries the id everything else is moved onto, and the seal cut against that id.

    Byte-for-byte rather than field-by-field, because this is the one event whose exact payload the client stores and replays. Verified the same way against both real captures.
    """
    done = SseEvent(
        "response.output_item.done",
        orjson.dumps(drifting_item(0, "closed", seal="the-real-seal")).decode(),
    )

    (result,) = stabilise_stream_ids((done,))

    assert result.data == done.data


def test_a_seal_whose_id_is_being_rewritten_goes_with_it() -> None:
    """Upstream puts a partial seal on the opening event too, under that event's own id.

    Measured 2026-09-02: 4,888 bytes on `added`, 5,032 on `done`, different ids. Rewriting the opening id while keeping its seal would hand the client exactly the pair upstream refuses — GitHub issue #4, manufactured here rather than inherited. The complete seal is on the closing event, which is untouched, so nothing the client needs is lost.
    """
    events = [
        SseEvent("response.output_item.added", orjson.dumps(drifting_item(0, "opened", seal="partial")).decode()),
        SseEvent("response.output_item.done", orjson.dumps(drifting_item(0, "closed", seal="complete")).decode()),
    ]

    added, done = stabilised(events)

    assert added["item"]["id"] == "closed"
    assert "encrypted_content" not in added["item"]
    assert done["item"]["encrypted_content"] == "complete"


def test_an_item_still_open_at_this_boundary_is_left_alone() -> None:
    """Nothing to stabilise onto yet: its closing event is in a later batch, along with the rest of it.

    §4 guarantees an item's events never straddle a release boundary, so this case is a batch that ends *before* the item opens — a control event run — rather than a torn item. Leaving it untouched is what keeps the reshape from inventing an id upstream never sent.
    """
    orphan = SseEvent(
        "response.output_text.delta",
        orjson.dumps({"output_index": 7, "item_id": "no-closing-event-here", "delta": "x"}).decode(),
    )

    (result,) = stabilise_stream_ids((orphan,))

    assert result.data == orphan.data


def test_the_envelope_settles_on_one_response_id_including_the_items_it_lists() -> None:
    """Three ids for one response is what upstream sends; a client correlating on it sees three responses.

    `response.completed` repeats the finished items positionally in `output`, so those ids are stabilised too — otherwise a client reading the turn off that array instead of off the item events would still see the drift, just somewhere harder to notice.
    """
    events = [
        SseEvent("response.created", orjson.dumps({"response": {"id": "first"}}).decode()),
        SseEvent("response.output_item.done", orjson.dumps(drifting_item(0, "closed")).decode()),
        SseEvent(
            "response.completed",
            orjson.dumps({"response": {"id": "third", "output": [{"type": "reasoning", "id": "yet-another"}]}}).decode(),
        ),
    ]

    created, _, completed = stabilised(events)

    assert created["response"]["id"] == "first"
    assert completed["response"]["id"] == "first"
    assert completed["response"]["output"][0]["id"] == "closed"


def test_nothing_is_added_dropped_or_reordered() -> None:
    """The reshape edits ids. Everything else about the stream is upstream's, including its shape.

    `sequence_number` in particular: it is upstream's own counter, and renumbering it would claim this proxy composed the stream. Asserted here rather than left to review because a reshape that starts tidying is how a named contract turns back into a translation.
    """
    events = [
        SseEvent("response.created", orjson.dumps({"response": {"id": "r"}, "sequence_number": 0}).decode()),
        SseEvent("response.output_item.added", orjson.dumps({**drifting_item(0, "opened"), "sequence_number": 1}).decode()),
        SseEvent("response.output_item.done", orjson.dumps({**drifting_item(0, "closed"), "sequence_number": 2}).decode()),
    ]

    result = stabilise_stream_ids(tuple(events))

    assert [e.event for e in result] == [e.event for e in events]
    assert [orjson.loads(e.data)["sequence_number"] for e in result] == [0, 1, 2]


def test_a_second_closing_event_for_one_item_is_recorded(caplog: pytest.LogCaptureFixture) -> None:
    """The one upstream shape that can make a single-slot client render an answer twice.

    Codex takes an item out of its slot on `response.output_item.done`; a second one for the same `output_index` finds the slot empty, synthesises a fresh started/completed pair, and renders the whole text again as ordinary content. Read from Codex 0.144.1's own source, not inferred — `.dev/docs/direct-passthrough/reports/260902-duplicate-delivery-hunt.md`, which reached this shape by exhausting 207 mutations of an upstream sequence: all 21 that reproduced the symptom were this one.

    **The translating leg swallowed it and this leg forwards it**, so the change of behaviour is real and is `1fb37cd`'s. What is *not* established is that upstream ever sends it: every capture this project holds carries exactly one closing event per item, and the request log keeps no bodies. That is why this records rather than drops — dropping would change what a native leg promises (§2.1) on the strength of a guess, and one real session with this line in place settles it. `deferred.md` D-9.

    Asserted on the log because the delivery is deliberately unchanged: the assertion that nothing else moved is the second half.
    """
    assembler = responses_passthrough_assembler()
    closing = event("response.output_item.done", output_index=0, item={"id": "m", "type": "message"})

    with caplog.at_level("WARNING"):
        first = assembler.push(closing)
        second = assembler.push(closing)

    assert "closed output_index 0 twice" in caplog.text
    # Still carried, both times. This leg does not decide what upstream may say.
    assert [e for batch in first for e in batch.events] == [closing]
    assert [e for batch in second for e in batch.events] == [closing]


def test_one_closing_event_per_item_says_nothing(caplog: pytest.LogCaptureFixture) -> None:
    """The control, and it is the half that makes the warning worth having.

    A detector that fires on the ordinary stream tells an operator nothing and trains them to ignore it. This is the shape all three of the project's real recordings carry.
    """
    assembler = responses_passthrough_assembler()

    with caplog.at_level("WARNING"):
        assembler.push(event("response.output_item.added", output_index=0, item={"id": "m", "type": "message"}))
        assembler.push(event("response.output_item.done", output_index=0, item={"id": "m", "type": "message"}))
        assembler.push(event("response.output_item.added", output_index=1, item={"id": "n", "type": "message"}))
        assembler.push(event("response.output_item.done", output_index=1, item={"id": "n", "type": "message"}))

    assert caplog.text == ""
