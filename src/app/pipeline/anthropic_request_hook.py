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
    """Whether upstream would reject this block for carrying no text.

    `.strip()` rather than `== ""` because upstream rejects whitespace separately and says so in its own words: alongside `text content blocks must be non-empty` it answers `text content blocks must contain non-whitespace text`. One predicate covers both, and it is the same one `filter_empty_text_blocks` and the reference implementation already use.

    A missing or null `text` counts as blank. A `text` that is not a string does not: this fixup exists to drop blocks that carry nothing, and quietly deleting a malformed one would hide a client bug behind a rewrite instead of letting upstream name it.
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


def drop_blank_text(content: list[Any], *, field: str) -> list[Any]:
    """Remove text blocks upstream will reject, unless they are all this field has.

    A blank text block carries nothing, so dropping it cannot change what the model is being told — which is what makes this safe to do without asking. Leaving it in costs the whole request: upstream rejects the entire body over one such block, and the client's next turn replays the same history and is rejected again.

    The all-blank case is deliberately left alone. Emptying the list to `[]` trades one rejection for another, and the alternatives — deleting the message, or inventing filler text for it — either break the user/assistant sequence the rest of the history is paired against or put words in someone's mouth. Failing exactly as before is the honest outcome, so it is logged rather than patched.

    `field` names where this ran, because the same rule covers `messages` and `system` and a log line that guessed would send a reader to the wrong half of the body.
    """
    kept = [block for block in content if not _is_blank_text(block)]
    if len(kept) == len(content):
        return content
    if not kept:
        logger.warning(
            "every block in %s is blank text; upstream will reject this request and there is no rewrite that preserves its meaning",
            field,
        )
        return content
    logger.debug("dropped %d blank text block(s) from %s that upstream would have rejected", len(content) - len(kept), field)
    return kept


def fix_anthropic_request(
    payload: dict[str, Any], config: FixAnthropicRequestHook, *, upstream_is_anthropic: bool
) -> None:
    """Apply the configured request fixups in place.

    In place because the caller owns the payload and the next step reads it from the same context;
    returning a copy would leave two versions and no rule about which one travels.

    `upstream_is_anthropic` is required rather than defaulted: it decides whether the fixups that exist only to satisfy the Anthropic upstream's contract run at all, and a default would silently pick one of the two legs for any caller that forgot to say which it was on.
    """
    # Before the messages guard below: this one is about a top-level field, and a body with no
    # `messages` list still carries it.
    normalize_context_management(payload)

    # `system` is rejected on the same grounds as `messages`, and it is a sibling top-level field rather than part of a turn, so it is handled here rather than in the loop. A string `system` has no blocks to drop.
    system_value = payload.get("system")
    if upstream_is_anthropic and isinstance(system_value, list):
        payload["system"] = drop_blank_text(cast(list[Any], system_value), field="system")

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

        # Before the layout pass for the same reason, and for a second one: a blank text block sitting between two thinking blocks makes them look non-adjacent, so the layout would leave the pair upstream rejects while the blank block earns its own rejection. Removing it first lets the layout see the adjacency and spend a real separator on it.
        # Gated on the outbound upstream because only the Anthropic one is known to refuse these. On the Responses leg a blank block is currently carried into the joined `instructions` string and into the text parts, and dropping it there would change bytes this defect never asked us to change.
        if upstream_is_anthropic:
            content = cast(
                list[dict[str, Any]],
                drop_blank_text(cast(list[Any], content), field="messages"),
            )

        # Only assistant turns can hit the adjacency rejection the layout exists to avoid.
        if entry.get("role") == "assistant":
            content, _ = destack_content(content, strategy)

        entry["content"] = content
