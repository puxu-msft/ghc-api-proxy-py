"""The `hook_fix_anthropic_request` fixups, applied while the body is still Anthropic-shaped.

Order matters and it is the reason this runs where it does. `handler.handle()` translates before it
drives, so by the time the driver publishes `attempt.prepare` the payload is in the *target* format
— Responses on the primary path. An Anthropic-request fixup applied there would be looking at a
body that no longer has `messages` at all. This is the spec's `on_client_request_parsed` moment.

Nothing here is new logic. `destack_content` and `sanitize_empty_thinking` already implement what
the spec asks for; what was missing is anything on the new chain calling them.
`drop_blank_text` is the same story told a third time: `app.anthropic.sanitize.text_blocks.filter_empty_text_blocks` has carried this rule since the existing chain was written, and the new chain simply never called it.
"""

import logging
from typing import Any, cast

from app.anthropic.thinking.destack import DestackStrategy, destack_content
from app.anthropic.thinking.protection import sanitize_empty_thinking
from app.config.schema import AssistantMessageLayout, FixAnthropicRequestHook

logger = logging.getLogger(__name__)

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


def _is_blank_text(block: Any) -> bool:
    """Whether this block carries no text at all.

    That is the whole criterion, and it is a property of the block rather than of whoever receives it: a text block whose text is empty or only whitespace says nothing, so nothing downstream can be reading it. `.strip()` rather than `== ""` because whitespace is not text either — corroborated by the Anthropic upstream, which refuses the two separately and in its own words, `text content blocks must be non-empty` alongside `text content blocks must contain non-whitespace text`. It is the same predicate `filter_empty_text_blocks` and the reference implementation already use.

    A missing or null `text` counts as blank. A `text` that is not a string does not: this fixup exists to drop blocks that carry nothing, and quietly deleting a malformed one would hide a client bug behind a rewrite instead of letting the receiver name it.
    """
    if not isinstance(block, dict):
        return False
    entry = cast(dict[str, Any], block)
    if entry.get("type") != "text":
        return False
    text = entry.get("text")
    if text is None:
        return True
    return isinstance(text, str) and not text.strip()


def drop_blank_text(content: list[Any]) -> list[Any]:
    """Every block except the ones that carry no text.

    Unconditional, and with nothing to configure: removing a block that says nothing cannot change what the model is being told, so there is no case in which keeping it is the better answer. Keeping one can cost the whole request, which is how this was found.

    Returns the argument itself when nothing matched, so an untouched body stays the object it arrived as and a caller can tell "nothing to do" from "everything went" by identity. Deciding what an empty result means is the caller's, because the answer differs by field — see `fix_anthropic_request` — which is also why nothing is logged here: at this point it is not yet known whether the result will be used.
    """
    kept = [block for block in content if not _is_blank_text(block)]
    return content if len(kept) == len(content) else kept


def fix_anthropic_request(payload: dict[str, Any], config: FixAnthropicRequestHook) -> None:
    """Apply the configured request fixups in place.

    In place because the caller owns the payload and the next step reads it from the same context;
    returning a copy would leave two versions and no rule about which one travels.
    """
    # Before the messages guard below: this one is about a top-level field, and a body with no
    # `messages` list still carries it.
    normalize_context_management(payload)

    # `system` carries the same blocks and is a sibling top-level field rather than part of a turn, so it is handled here rather than in the loop. A string `system` has no blocks to drop.
    system_value = payload.get("system")
    if isinstance(system_value, list):
        system = cast(list[Any], system_value)
        kept = drop_blank_text(system)
        if kept is not system:
            if kept:
                payload["system"] = kept
                logger.debug("dropped %d blank block(s) from system", len(system) - len(kept))
            else:
                # A system prompt made of nothing but blank blocks says exactly as much as no system prompt, and the second spelling is one every upstream takes. `[]` is neither.
                del payload["system"]
                logger.debug("system carried nothing but blank blocks; the field is gone rather than empty")

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

        # Before the layout pass for the same reason, and for a second one: a blank text block sitting between two thinking blocks makes them look non-adjacent, so the layout would leave a pair the Anthropic upstream refuses while the blank block earns its own rejection. Removing it first lets the layout see the adjacency and spend a real separator on it.
        kept_content = cast(list[dict[str, Any]], drop_blank_text(cast(list[Any], content)))
        if kept_content:
            if kept_content is not content:
                logger.debug("dropped %d blank block(s) from a message", len(content) - len(kept_content))
            content = kept_content
        else:
            # Unlike `system`, a turn cannot be dropped for saying nothing: the rest of the history is paired against it by position, and `tool_result` blocks name a `tool_use` in the turn before. Emptying it to `content: []` would invent a body the client never sent, so the turn goes out as it arrived and whoever receives it gets to say what is wrong with it.
            logger.warning(
                "a message carries nothing but blank text blocks; it is being sent unchanged, because dropping the turn or emptying its content would break the sequence the rest of the history is paired against",
            )

        # Only assistant turns can hit the adjacency rejection the layout exists to avoid.
        if entry.get("role") == "assistant":
            content, _ = destack_content(content, strategy)

        entry["content"] = content
