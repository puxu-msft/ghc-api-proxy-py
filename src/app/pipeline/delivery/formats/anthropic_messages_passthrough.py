"""The `anthropic-messages` vocabulary for the direct-leg passthrough engine.

`spec.md` §2.5 defines what a dialect answers; `delivery/passthrough.py` is the engine that asks. This module holds only the Anthropic answers.

**Why this leg matters more than its position in the plan suggests.** `claude-sonnet-5` does not support the Responses API at all — measured, `unsupported_api_for_model` — so Claude models can only be served direct, and this is the leg they take. The round trip it runs today has the same ceiling issues #1 through #3 landed on: an unknown content-block kind is refused by `AnthropicFramer` rather than carried. `spec.md` §2.6.

**What this leg does *not* stop doing.** `hook_fix_anthropic_sse.thinking.content_block_start_compat` defaults to `signature_delta`, so every Anthropic leg today lifts an embedded thinking signature into its own event. `spec.md` §2.7 rules that wiring must not change any leg's effective reshape defaults — going native is about removing a translation nobody asked for, not about removing a compatibility layer the user leans toward making permanent (`deferred.md` D-4).
"""

from typing import Any

from app.pipeline.delivery.assembling import (
    ClientActionRequirement,
    ReplyDialect,
    Terminal,
)
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


def client_action_requirement(item: dict[str, Any]) -> ClientActionRequirement:
    """Classify the content block in Anthropic's single-action vocabulary.

    A `tool_use` block always means the client owes the model something, and nothing else does. An unknown block type is therefore not required here: unlike an unknown Responses item, it is new content rather than a new spelling for a client action.
    """
    if item.get("type") == TOOL_USE:
        return ClientActionRequirement.REQUIRED
    return ClientActionRequirement.NOT_REQUIRED


def requires_client_action(item: dict[str, Any]) -> bool:
    """Project the classifier onto the buffering policy's boolean."""
    return client_action_requirement(item) is not ClientActionRequirement.NOT_REQUIRED


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
    client_action_requirement=client_action_requirement,
    read_terminal=_read_terminal,
    read_failure=anthropic_failure_from,
)


def anthropic_passthrough_assembler() -> PassthroughAssembler:
    """The engine bound to this dialect. A function rather than a subclass: there is no behaviour to add."""
    return PassthroughAssembler(ANTHROPIC_DIALECT)
