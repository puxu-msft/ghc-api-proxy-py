"""The `hook_fix_anthropic_request` fixups, applied while the body is still Anthropic-shaped.

Order matters and it is the reason this runs where it does. `handler.handle()` translates before it
drives, so by the time the driver publishes `attempt.prepare` the payload is in the *target* format
— Responses on the primary path. An Anthropic-request fixup applied there would be looking at a
body that no longer has `messages` at all. This is the spec's `on_client_request_parsed` moment.

Nothing here is new logic. `destack_content` and `sanitize_empty_thinking` already implement what
the spec asks for; what was missing is anything on the new chain calling them.
"""

import logging
import re
from typing import Any, cast

from app.anthropic.thinking.destack import DestackStrategy, destack_content
from app.anthropic.thinking.protection import sanitize_empty_thinking
from app.config.schema import AssistantMessageLayout, FixAnthropicRequestHook

logger = logging.getLogger(__name__)

SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)

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


def tool_names_by_use_id(messages: list[Any]) -> dict[str, str]:
    """Which tool each `tool_use_id` belongs to, read off the assistant turns that made the calls.

    A `tool_result` does not say which tool produced it. Measured across 859 of them in this machine's own transcripts: the field set is exactly `content`, `is_error`, `tool_use_id`, `type` — no `tool_name`, ever. The name lives on the `tool_use` block in an earlier assistant turn, and the id is what joins them; that join resolved all 859.

    The existing chain's `strip_read_tool_result_tags` reads `block["tool_name"]` instead, which is why it does nothing on real traffic even where it is called.
    """
    names: dict[str, str] = {}
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = cast(dict[str, Any], message).get("content")
        if not isinstance(content, list):
            continue
        for block in cast(list[Any], content):
            if not isinstance(block, dict):
                continue
            entry = cast(dict[str, Any], block)
            identifier = entry.get("id")
            if entry.get("type") == "tool_use" and isinstance(identifier, str):
                name = entry.get("name")
                if isinstance(name, str):
                    names[identifier] = name
    return names


def strip_read_reminders(messages: list[Any]) -> int:
    """Remove `<system-reminder>` sections from Read results, returning the bytes saved.

    The client appends a general safety notice to every file it reads. It says the same thing each time, it is not about the file, and it is paid for in input tokens on this turn and on every turn that replays the conversation afterwards.

    Scoped to Read by the tool that made the call, because that is what the operator's key names and because the other reminders a client injects are not this one — a turn-level notice about tool use is addressed to the model's next decision, and removing it would change what the model was told rather than what it was billed for.

    **Returns the saving so this cannot fail quietly.** Where the notice actually sits in the outbound body could not be settled from transcripts: the client injects it while building the request, so it is absent from everything it stores — 83 Read results and 416 KB of recorded content contain none. If it turns out to ride somewhere other than the tool result, this removes nothing, and a caller that logs the return value will say so instead of leaving another switch that looks live and is not.
    """
    names = tool_names_by_use_id(messages)
    saved = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = cast(dict[str, Any], message).get("content")
        if not isinstance(content, list):
            continue
        for block in cast(list[Any], content):
            if not isinstance(block, dict):
                continue
            entry = cast(dict[str, Any], block)
            if entry.get("type") != "tool_result":
                continue
            use_id = entry.get("tool_use_id")
            if not isinstance(use_id, str) or names.get(use_id) != "Read":
                continue
            saved += _strip_in_place(entry)
    return saved


def _strip_in_place(result: dict[str, Any]) -> int:
    """Strip the notice from one `tool_result`, whichever of the two content shapes it uses.

    Both are real: of 859 recorded results, 835 carried a plain string and 23 carried a list of blocks.
    """
    saved = 0
    content = result.get("content")
    if isinstance(content, str):
        stripped = SYSTEM_REMINDER.sub("", content)
        saved += len(content) - len(stripped)
        result["content"] = stripped
        return saved
    if not isinstance(content, list):
        return 0
    for part in cast(list[Any], content):
        if not isinstance(part, dict):
            continue
        piece = cast(dict[str, Any], part)
        text = piece.get("text")
        if piece.get("type") != "text" or not isinstance(text, str):
            continue
        stripped = SYSTEM_REMINDER.sub("", text)
        saved += len(text) - len(stripped)
        piece["text"] = stripped
    return saved


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

    if config.strip_system_reminder_from_Read:
        # Here rather than at `attempt.prepare`, unlike the fixups that exist because one endpoint refuses a shape. Nobody refuses this one; it is bytes with no reader, so it is not a property of the leg. And the counting endpoint runs this same function: a strip applied after it would have `/v1/messages/count_tokens` measure a body larger than the one that gets sent, which for a saving measured in tokens is the wrong number to hand back.
        saved = strip_read_reminders(messages)
        if saved:
            logger.info("dropped %d bytes of Read tool reminders", saved)

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
