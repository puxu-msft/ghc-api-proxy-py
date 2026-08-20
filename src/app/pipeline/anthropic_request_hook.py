"""The `hook_fix_anthropic_request` fixups, applied while the body is still Anthropic-shaped.

Order matters and it is the reason this runs where it does. `handler.handle()` translates before it
drives, so by the time the driver publishes `attempt.prepare` the payload is in the *target* format
— Responses on the primary path. An Anthropic-request fixup applied there would be looking at a
body that no longer has `messages` at all. This is the spec's `on_client_request_parsed` moment.

Nothing here is new logic. `destack_content` and `sanitize_empty_thinking` already implement what
the spec asks for; what was missing is anything on the new chain calling them.
"""

from typing import Any, cast

from app.anthropic.thinking.destack import DestackStrategy, destack_content
from app.anthropic.thinking.protection import sanitize_empty_thinking
from app.config.schema import AssistantMessageLayout, FixAnthropicRequestHook

# The spec names the outcome; the existing implementation names the manoeuvre.
_LAYOUT_STRATEGY: dict[AssistantMessageLayout, DestackStrategy] = {
    False: "passthrough",
    "move_and_synthetic": "move_blocks",
    "synthetic_only": "insert_text",
}


def layout_strategy(layout: AssistantMessageLayout) -> DestackStrategy:
    """Map the configured layout onto the destack strategy that produces it.

    Total rather than defaulted: the schema now admits exactly the three spellings the spec
    defines, so a missing case would be a bug here rather than an operator's typo. A fallback
    would have turned an unhandled value into a silent rewrite of the request body.
    """
    return _LAYOUT_STRATEGY[layout]


def normalize_context_management(payload: dict[str, Any]) -> None:
    """Make `context_management` say "no edits" in the spelling upstream accepts.

    Claude Code sends `{"edits": null}` on every request. Upstream rejects that outright — with
    the `context-management-2025-06-27` beta it answers `context_management.edits: Input should be
    a valid array`, and without the beta it does not recognise the field at all. `{"edits": []}`
    is accepted, and so is dropping the key; the empty list is used because it preserves what the
    client actually said rather than pretending it said nothing.

    Measured against the live upstream on 2026-08-18, all three spellings.
    """
    value = payload.get("context_management")
    if not isinstance(value, dict):
        return
    management = cast(dict[str, Any], value)
    if "edits" in management and management["edits"] is None:
        management["edits"] = []


def fix_anthropic_request(payload: dict[str, Any], config: FixAnthropicRequestHook) -> None:
    """Apply the configured request fixups in place.

    In place because the caller owns the payload and the next step reads it from the same context;
    returning a copy would leave two versions and no rule about which one travels.
    """
    # Before the messages guard below: this one is about a top-level field, and a body with no
    # `messages` list still carries it.
    normalize_context_management(payload)

    messages_value = payload.get("messages")
    if not isinstance(messages_value, list):
        return
    messages = cast(list[Any], messages_value)

    strategy = layout_strategy(config.thinking.assistant_message_layout)
    strip_empty = config.thinking.strip_both_empty_thinking_blocks

    for message in messages:
        if not isinstance(message, dict):
            continue
        entry = cast(dict[str, Any], message)
        content_value = entry.get("content")
        if not isinstance(content_value, list):
            continue
        content = cast(list[dict[str, Any]], content_value)

        if strip_empty:
            # Before the layout pass: a block with neither signature nor text carries nothing, so
            # letting it separate two real thinking blocks would spend a separator on a placeholder.
            content, _ = sanitize_empty_thinking(content, "all_empty")

        # Only assistant turns can hit the adjacency rejection the layout exists to avoid.
        if entry.get("role") == "assistant":
            content, _ = destack_content(content, strategy)

        entry["content"] = content
