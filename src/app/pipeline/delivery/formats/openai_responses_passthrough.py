"""The `openai-responses` vocabulary for the direct-leg passthrough engine.

`spec.md` §2.5 defines what a dialect has to answer; `delivery/passthrough.py` is the engine that asks. This module holds only the Responses answers — the six facts about that wire, and the one predicate (§7.1) that needs more than a table.

**No item-type taxonomy lives here either.** `CONTROL_EVENTS` separates the envelope from everything else and never one item type from another, so an item this proxy has never heard of is grouped by its `output_index` without anything recognising it. The type sets below belong to `requires_client_action`, which answers a different question — whether the client owes the model something — and §7.1 explains why that one cannot be a pure table.
"""

from typing import Any

from app.pipeline.delivery.assembling import ReplyDialect, Terminal
from app.pipeline.delivery.formats.openai_responses import (
    read_responses_terminal,
    responses_failure_from,
)
from app.pipeline.delivery.passthrough import Dialect, PassthroughAssembler
from app.pipeline.delivery.sse_source import SseEvent
from app.pipeline.response_action import classify_responses_client_action

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
    """The established delivery answer, read from the shared observation classification.

    Observation keeps its tri-state requirement and the basis for that answer. This adapter reads the independent compatibility boolean because two unknown observations intentionally have opposite delivery behaviour: an unrecognised future item releases early, while a `tool_search_call` with no recognised execution value does not.
    """
    return classify_responses_client_action(item).delivery_required


def _read_terminal(event: SseEvent, terminal: Terminal, saw_client_action: bool) -> None:
    """Adapter onto the shared reader, which takes the event already split into name and payload.

    The reader is shared with the translating assembler on purpose (`openai_responses.read_responses_terminal`): both legs read the same terminal event for the same facts, and a second copy would be a second answer to what upstream's usage and stop reason are.
    """
    data = event.json()
    read_responses_terminal(
        event.event or str(data.get("type", "")),
        data,
        terminal,
        saw_tool_call=saw_client_action,
    )


RESPONSES_DIALECT = Dialect(
    name="openai-responses",
    reply_dialect=ReplyDialect.RESPONSES,
    control_events=CONTROL_EVENTS,
    terminal_events=TERMINAL_EVENTS,
    item_done_event=ITEM_DONE,
    # **Not** the item id. This upstream sends a different `item.id` on an item's `added` and `done`, so keying on the id pairs nothing — the defect `ResponsesAssembler._item_key` already records.
    item_index_field="output_index",
    requires_client_action=requires_client_action,
    read_terminal=_read_terminal,
    read_failure=responses_failure_from,
)


def responses_passthrough_assembler() -> PassthroughAssembler:
    """The engine bound to this dialect. A function rather than a subclass: there is no behaviour to add."""
    return PassthroughAssembler(RESPONSES_DIALECT)
