"""The `anthropic-messages` vocabulary for the direct-leg passthrough engine.

`spec.md` §2.5 defines what a dialect answers; `delivery/passthrough.py` is the engine that asks. This module holds only the Anthropic answers.

**Why this leg matters more than its position in the plan suggests.** `claude-sonnet-5` does not support the Responses API at all — measured, `unsupported_api_for_model` — so Claude models can only be served direct, and this is the leg they take. The round trip it runs today has the same ceiling issues #1 through #3 landed on: an unknown content-block kind is refused by `AnthropicFramer` rather than carried. `spec.md` §2.6.

**What this leg does *not* stop doing.** `hook_fix_anthropic_sse.thinking.content_block_start_compat` defaults to `signature_delta`, so every Anthropic leg today lifts an embedded thinking signature into its own event. `spec.md` §2.7 rules that wiring must not change any leg's effective reshape defaults — going native is about removing a translation nobody asked for, not about removing a compatibility layer the user leans toward making permanent (`deferred.md` D-4).
"""

from typing import Any

from app.pipeline.delivery.assembling import ReplyDialect, Terminal
from app.pipeline.delivery.blocks import TOOL_USE
from app.pipeline.delivery.formats.anthropic_messages import (
    anthropic_failure_from,
    read_anthropic_terminal,
)
from app.pipeline.delivery.passthrough import Dialect, PassthroughAssembler
from app.pipeline.delivery.sse_source import SseEvent

# The message envelope: events belonging to no content block.
#
# `ping` is in here because it is upstream's own keep-alive event, and on this leg it is carried like any other envelope event rather than swallowed — the client asked for this dialect and a `ping` is part of it.
CONTROL_EVENTS = frozenset(
    {
        "message_start",
        "message_delta",
        "message_stop",
        "ping",
        "error",
    }
)

# `message_delta` is deliberately **not** here. It carries the stop reason and usage but does not end anything — this dialect splits its ending across two events, and only the second closes. Putting `message_delta` in would let a prefix containing nothing but it be delivered on its own, which §4 forbids.
TERMINAL_EVENTS = frozenset({"message_stop", "error"})

ITEM_DONE = "content_block_stop"


def requires_client_action(item: dict[str, Any]) -> bool:
    """Whether this content block stops the turn until the client submits a tool result.

    One line rather than §7.1's whole section, because this dialect has no conditional field: a `tool_use` block always means the client owes the model something, and nothing else does. The Responses side needs more because the same `tool_search_call` answers oppositely depending on `execution`.

    An unknown block type answers `False` here, and that is not the Responses rule inverted — it is the same rule applied to a different set. On the Responses side an unknown *item* may well be a tool call this proxy has not heard of. Here the vocabulary is Anthropic's own content-block types, where `tool_use` is the single spelling for "the client must act"; a new kind of block would be new *content*, not a new way of asking the client for something.
    """
    return str(item.get("type", "")) == TOOL_USE


def _read_terminal(event: SseEvent, terminal: Terminal, saw_client_action: bool) -> None:
    """Adapter onto the shared reader.

    `saw_client_action` is unused: unlike the Responses leg, this dialect's upstream states its own stop reason on `message_delta`, so nothing has to be inferred from whether a tool was called.
    """
    read_anthropic_terminal(event, terminal)


ANTHROPIC_DIALECT = Dialect(
    name="anthropic-messages",
    reply_dialect=ReplyDialect.ANTHROPIC,
    control_events=CONTROL_EVENTS,
    terminal_events=TERMINAL_EVENTS,
    item_done_event=ITEM_DONE,
    item_index_field="index",
    requires_client_action=requires_client_action,
    read_terminal=_read_terminal,
    read_failure=anthropic_failure_from,
)


def anthropic_passthrough_assembler() -> PassthroughAssembler:
    """The engine bound to this dialect. A function rather than a subclass: there is no behaviour to add."""
    return PassthroughAssembler(ANTHROPIC_DIALECT)
