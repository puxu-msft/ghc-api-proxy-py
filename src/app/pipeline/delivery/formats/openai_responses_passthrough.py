"""The `openai-responses` vocabulary for the direct-leg passthrough engine.

`spec.md` §2.5 defines what a dialect has to answer; `delivery/passthrough.py` is the engine that asks. This module holds only the Responses answers — the six facts about that wire, and the one predicate (§7.1) that needs more than a table.

**No item-type taxonomy lives here either.** `CONTROL_EVENTS` separates the envelope from everything else and never one item type from another, so an item this proxy has never heard of is grouped by its `output_index` without anything recognising it. The type sets below belong to `requires_client_action`, which answers a different question — whether the client owes the model something — and §7.1 explains why that one cannot be a pure table.
"""

from typing import Any, cast

import orjson

from app.pipeline.delivery.assembling import (
    ClientActionRequirement,
    ReplyDialect,
    Terminal,
)
from app.pipeline.delivery.formats.openai_responses import (
    read_responses_terminal,
    responses_failure_from,
)
from app.pipeline.delivery.formats.openai_responses_actions import (
    client_action_requirement,
    read_responses_client_actions,
)
from app.pipeline.delivery.passthrough import Dialect, PassthroughAssembler
from app.pipeline.delivery.sse_source import SseEvent

# The response envelope: events belonging to no output item.
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

# The envelope events that end a response. `spec.md` §5's commit table gives an item-less terminal a row of its own: a response with no output items at all is `created → completed`, and a terminal is also the point after which there is nothing left to replay.
TERMINAL_EVENTS = frozenset(
    {
        "response.completed",
        "response.incomplete",
        "response.failed",
        "response.cancelled",
        "error",
    }
)

ITEM_DONE = "response.output_item.done"


def requires_client_action(item: dict[str, Any]) -> bool:
    """Project the three-state fact onto the conservative buffering decision."""
    return client_action_requirement(item) is not ClientActionRequirement.NOT_REQUIRED


def _read_terminal(event: SseEvent, terminal: Terminal, saw_client_action: bool) -> None:
    """Read shared semantics, then the direct completed terminal's native facts."""
    data = event.json()
    kind = event.event or str(data.get("type", ""))
    read_responses_terminal(
        kind,
        data,
        terminal,
        saw_tool_call=saw_client_action,
    )
    if kind != "response.completed":
        return
    raw_response = data.get("response")
    response = cast(dict[str, Any], raw_response) if isinstance(raw_response, dict) else {}
    raw_status = response.get("status")
    terminal.terminal_status = raw_status if isinstance(raw_status, str) and raw_status else "completed"
    actions, classification_complete = read_responses_client_actions(response)
    terminal.client_actions = actions
    terminal.client_action_classification_complete = classification_complete


RESPONSES_DIALECT = Dialect(
    name="openai-responses",
    reply_dialect=ReplyDialect.RESPONSES,
    control_events=CONTROL_EVENTS,
    terminal_events=TERMINAL_EVENTS,
    item_done_event=ITEM_DONE,
    # **Not** the item id. This upstream sends a different `item.id` on an item's `added` and `done`, so keying on the id pairs nothing — the defect `ResponsesAssembler._item_key` already records.
    item_index_field="output_index",
    client_action_requirement=client_action_requirement,
    read_terminal=_read_terminal,
    read_failure=responses_failure_from,
)


def responses_passthrough_assembler() -> PassthroughAssembler:
    """The engine bound to this dialect. A function rather than a subclass: there is no behaviour to add."""
    return PassthroughAssembler(RESPONSES_DIALECT)


# --- `fix_stream_ids`: the declared reshape of §6.6 -------------------------------


def _rewrite_item_ids(payload: dict[str, Any], item_id: str) -> bool:
    """Point this event's id fields at `item_id`. Answers whether anything changed.

    Both spellings, because this wire uses two: the item object carries `id` on the opening and closing events, and every event in between carries a sibling `item_id` instead.
    """
    changed = False
    if payload.get("item_id") not in (None, item_id):
        payload["item_id"] = item_id
        changed = True
    item = payload.get("item")
    if isinstance(item, dict):
        entry = cast(dict[str, Any], item)
        if entry.get("id") not in (None, item_id):
            entry["id"] = item_id
            changed = True
            # The seal is cut against the id that arrived with it. Rewriting the id and keeping the seal hands the client the pair upstream refuses — issue #4, by our own hand this time. The closing event never reaches here, so the complete seal still travels; what is dropped is a partial one under an id that no longer matches it.
            if entry.pop("encrypted_content", None) is not None:
                changed = True
    return changed


def stabilise_stream_ids(events: tuple[SseEvent, ...]) -> tuple[SseEvent, ...]:
    """Give every event of one output item the id its **closing** event carries.

    `spec.md` §6.6. Off unless configured: this rewrites upstream's bytes, and §2.7 forbids calling such a thing native.

    **Closing rather than first-seen, and that is the whole difficulty.** Measured 2026-09-02: one reasoning item arrived with a 4,888-byte seal under one id on `added` and a 5,032-byte seal under a different id on `done`. Each seal is bound to the id it came with, and upstream verifies that binding when the item is replayed. Stabilising onto the opening id would attach the closing seal to the opening id — issue #4 exactly, manufactured here rather than inherited. Stabilising onto the closing id leaves the pair the client actually stores untouched.

    **Only block-level delivery makes this possible.** A stream forwarded event by event cannot know, when `added` goes out, what id `done` will carry. This engine releases a whole batch at once, and §4 guarantees an item's events never straddle a batch — so a batch holding an item's closing event holds all of them, and the answer is already in hand. An item still open at this boundary is left alone: nothing to stabilise onto yet, and its events are all still ahead.

    Envelope events take the `response.id` of the first one seen. No seal is bound to it, so any choice is safe; first rather than last because that is the id a client has already logged by the time the others arrive.

    Byte fidelity is spent only where an id actually changed — untouched events keep the exact text they arrived as. That is the declared cost of the reshape, and it is why this is a named contract rather than part of the leg.
    """
    parsed = [(event, event.json()) for event in events]

    closing: dict[object, str] = {}
    for event, payload in parsed:
        if event.event != ITEM_DONE:
            continue
        item = payload.get("item")
        if isinstance(item, dict):
            item_id = cast(dict[str, Any], item).get("id")
            if isinstance(item_id, str):
                closing[payload.get("output_index")] = item_id

    envelope_id: str | None = None
    for event, payload in parsed:
        if event.event not in CONTROL_EVENTS:
            continue
        response = payload.get("response")
        if isinstance(response, dict):
            candidate = cast(dict[str, Any], response).get("id")
            if isinstance(candidate, str):
                envelope_id = candidate
                break

    out: list[SseEvent] = []
    for event, payload in parsed:
        if event.event in CONTROL_EVENTS:
            changed = _rewrite_envelope(payload, envelope_id, closing)
        elif event.event == ITEM_DONE:
            # Untouched on purpose: it is the id everything else is being moved onto, and the one its seal was cut against.
            changed = False
        else:
            item_id = closing.get(payload.get("output_index"))
            changed = _rewrite_item_ids(payload, item_id) if item_id is not None else False
        out.append(SseEvent(event.event, orjson.dumps(payload).decode()) if changed else event)
    return tuple(out)


def _rewrite_envelope(
    payload: dict[str, Any], envelope_id: str | None, closing: dict[object, str]
) -> bool:
    """The `response.id` an envelope event reports, and the ids of the items it lists.

    `response.completed` repeats the finished items in `output`, positionally — `output[i]` is the item whose events carried `output_index` i. A client that reads the turn off that array rather than off the item events has to see the same ids, or stabilising the events alone would just move the inconsistency somewhere less visible.
    """
    response = payload.get("response")
    if not isinstance(response, dict):
        return False
    envelope = cast(dict[str, Any], response)
    changed = False
    if envelope_id is not None and envelope.get("id") not in (None, envelope_id):
        envelope["id"] = envelope_id
        changed = True
    listed = envelope.get("output")
    if isinstance(listed, list):
        for index, item in enumerate(cast(list[Any], listed)):
            if not isinstance(item, dict):
                continue
            item_id = closing.get(index)
            entry = cast(dict[str, Any], item)
            if item_id is not None and entry.get("id") not in (None, item_id):
                entry["id"] = item_id
                changed = True
    return changed
