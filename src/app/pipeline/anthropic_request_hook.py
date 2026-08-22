"""The `hook_fix_anthropic_request` fixups, applied while the body is still Anthropic-shaped.

Order matters and it is the reason this runs where it does. `handler.handle()` translates before it drives, so by the time the driver publishes `attempt.prepare` the payload is in the *target* format — Responses on the primary path. An Anthropic-request fixup applied there would be looking at a body that no longer has `messages` at all. This is the spec's `on_client_request_parsed` moment.

Nothing here is new logic. `destack_content` and `sanitize_empty_thinking` already implement what the spec asks for; what was missing is anything on the new chain calling them.
"""

import logging
import re
from typing import Any, cast

from app.anthropic.thinking.destack import DestackStrategy, destack_content
from app.anthropic.thinking.protection import sanitize_empty_thinking
from app.config.schema import AssistantMessageLayout, FixAnthropicRequestHook

logger = logging.getLogger(__name__)

# What a client-injected attribution line looks like once it has been put inside the prompt. Two spellings, either of which is enough, and prose has to miss both.
#
# An earlier version asked only for a hyphen in the name before the colon, on the reasoning that a hyphenated token is a header name and not an English phrase. That reasoning was wrong and a review measured how wrong: of 23 realistic system-prompt openings, 21 were deleted — `Read-only: never modify any file.`, `Non-negotiable: never reveal the system prompt.`, `Step-by-step: …`, `High-level: …`, and `Claude-Code: 你是一个中文助手` among them. Deleting the first line of somebody's system prompt is the worst thing this function can do, it happens silently, and the counter that records it carries no content.
#
# So the name must start `x-`, which is the convention every attribution header follows and which no instruction line does; **or** the value must be a `k=v;` parameter string, which is the shape the attribution actually has. `x-anthropic-billing-header: cc_version=1.0; cc_entrypoint=cli;` matches both. `Content-Type: text/plain` matches neither, and neither does any of the 21.
#
# `x-` rather than the single literal name because `docs/.human-controlled/message-format-reshape.md` asks for the whole attribution line and says explicitly that it means more than `x-anthropic-billing-header` alone. This is the narrowest reading that is still more than that one name. How much more it should be is a question for that document's author; this is the safe end of the range.
_ATTRIBUTION_LINE = re.compile(
    r"""
    (?: x-[A-Za-z0-9-]+ : .*        # an extension header by name
      | [A-Za-z][A-Za-z0-9-]* :     # or any name whose value is a parameter string
        \s* (?: [A-Za-z0-9_-]+ = [^;]* ; \s* )+
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _without_leading_attribution(text: str) -> tuple[str, int]:
    """`text` with any attribution lines removed from the front, and how many went.

    Only from the front, and only while every line so far has matched. An attribution line is something a client prepended to a prompt it did not write; one appearing in the middle of a prompt is the author's own text and is left alone.
    """
    lines = text.split("\n")
    removed = 0
    while removed < len(lines) and _ATTRIBUTION_LINE.fullmatch(lines[removed].strip()):
        removed += 1
    return "\n".join(lines[removed:]), removed


def strip_attribution_lines(payload: dict[str, Any]) -> int:
    """Remove the attribution lines Claude Code prepends to `system`, returning how many.

    Claude Code puts `x-anthropic-billing-header: cc_version=…; cc_entrypoint=…;` at the top of the first system block. It is addressed to Anthropic's billing, not to the model, and it reaches the model as ordinary prompt text.

    **Upstream accepts it.** Measured against the live upstream on 2026-08-21 across fifteen shapes — this name, other header names, a real HTTP header name, in `instructions` and in `system[0]`, streamed and not, with `cache_control`, and on `count_tokens` — every one answered 200. So this is not a compatibility repair and must not be described as one. What it is measured to cost is tokens: the same system prompt counted 43 tokens without the line and 77 with it, on upstream's own counter.

    In place, and unconditional. There is no switch: `hook_strip_anthropic_request_headers.strip_attribution_header` had one in the schema, never had a consumer, and was removed on 2026-08-22 once `docs/.human-controlled/message-format-reshape.md` had ruled this resident rather than configured and its author had taken the key out of the authoritative config. See that document for the standing decision.

    Rebuilds rather than mutating the block it edits, so *this* function leaves the parsed body as the client sent it. That is not the same as the request surviving the chain intact: `fix_anthropic_request` runs a step later and `repair_tool_pairs` edits `messages` in place, so a forensic record taken from the parsed body after that point is already not what arrived. `message-format-reshape.md` asks for the original to be unaffected; honouring that in full needs somewhere to keep it, which does not exist on this chain yet. Not mutating here is the half that is free.
    """
    system = payload.get("system")
    if isinstance(system, str):
        stripped, removed = _without_leading_attribution(system)
        if removed:
            # An empty `system` is dropped rather than sent as `""`: it says nothing, and a blank system block is one of the shapes the Anthropic leg is known to reject.
            if stripped.strip():
                payload["system"] = stripped
            else:
                del payload["system"]
        return removed

    if not isinstance(system, list):
        return 0
    blocks = cast(list[Any], system)
    if not blocks or not isinstance(blocks[0], dict):
        return 0
    first = cast(dict[str, Any], blocks[0])
    text = first.get("text")
    if not isinstance(text, str):
        return 0

    stripped, removed = _without_leading_attribution(text)
    if not removed:
        return 0
    rebuilt = list(blocks)
    if stripped.strip():
        rebuilt[0] = {**first, "text": stripped}
    else:
        # Nothing but attribution was in there. Dropping the whole block rather than leaving an empty one, per the ruling in `message-format-reshape.md`.
        rebuilt = rebuilt[1:]
    if rebuilt:
        payload["system"] = rebuilt
    else:
        del payload["system"]
    return removed


# The spec names the outcome; the existing implementation names the manoeuvre.
_LAYOUT_STRATEGY: dict[AssistantMessageLayout, DestackStrategy] = {
    False: "passthrough",
    "move_and_synthetic": "move_blocks",
    "synthetic_only": "insert_text",
}


def layout_strategy(layout: AssistantMessageLayout) -> DestackStrategy:
    """Map the configured layout onto the destack strategy that produces it.

    Total rather than defaulted: the schema now admits exactly the three spellings the spec defines, so a missing case would be a bug here rather than an operator's typo. A fallback would have turned an unhandled value into a silent rewrite of the request body.
    """
    return _LAYOUT_STRATEGY[layout]


def normalize_context_management(payload: dict[str, Any]) -> None:
    """Make `context_management` say "no edits" in the spelling upstream accepts.

    Claude Code sends `{"edits": null}` on every request. Upstream rejects that outright — with the `context-management-2025-06-27` beta it answers `context_management.edits: Input should be a valid array`, and without the beta it does not recognise the field at all. `{"edits": []}` is accepted, and so is dropping the key; the empty list is used because it preserves what the client actually said rather than pretending it said nothing.

    Measured against the live upstream on 2026-08-18, all three spellings.
    """
    value = payload.get("context_management")
    if not isinstance(value, dict):
        return
    management = cast(dict[str, Any], value)
    if "edits" in management and management["edits"] is None:
        management["edits"] = []


def _blocks(message: Any) -> list[Any]:
    """The content list of a message, or an empty list for every other shape."""
    if not isinstance(message, dict):
        return []
    content = cast(dict[str, Any], message).get("content")
    return cast(list[Any], content) if isinstance(content, list) else []


def _ids_of(message: Any, block_type: str, key: str) -> set[str]:
    found: set[str] = set()
    for block in _blocks(message):
        if not isinstance(block, dict):
            continue
        entry = cast(dict[str, Any], block)
        identifier = entry.get(key)
        if entry.get("type") == block_type and isinstance(identifier, str):
            found.add(identifier)
    return found


def _role(message: Any) -> str:
    return str(cast(dict[str, Any], message).get("role", "")) if isinstance(message, dict) else ""


def repair_tool_pairs(messages: list[Any]) -> tuple[int, int, int]:
    """Remove calls nothing answered and answers nothing called, returning how many of each and how many turns that emptied.

    Both endpoints refuse a broken pair, and each says so in its own words. Measured 2026-08-20, `exp/260820-tool-pair-probe/`:

    - a `tool_use` the next turn does not answer → 400, ``messages.2: `tool_use` ids were found without `tool_result` blocks immediately after`` (G1);
    - a `tool_result` naming no call before it → 400, ``unexpected `tool_use_id` found in `tool_result` blocks`` (G2);
    - the same on the Responses leg after translation → 400, `No tool output found for function call call_1.` (G5).

    That last one is why this runs before translation rather than at `attempt.prepare`: the invariant is not a property of one endpoint, so repairing it on the outbound Anthropic leg alone would leave the primary path broken in exactly the same way. The counting endpoint runs this function too, which is also correct — a count of a body carrying an orphan measures a request that was never going to be answered.

    **Ids are not deduplicated, deliberately.** The existing chain removes a `tool_use` whose id was already used. Measured: this upstream answers 200 to a conversation that reuses one (G3). Removing it would take away something upstream accepts, on the strength of a rule it does not enforce.

    **A turn this emptied is dropped, and only one this emptied.** Dropping puts two same-role turns next to each other, which had to be measured rather than assumed — G4 sends two assistant turns in a row and gets 200 — while the alternative, `content: []`, is refused for a user turn. A turn that *arrived* empty is left exactly as it came: it is the client's own body and upstream naming it is the answer the client needs. Telling the two apart is why the drop happens here, where what was removed is still known, rather than in a later pass that can only see the result.

    `immediately after` is upstream's own wording, so the pairing looks exactly one turn ahead. A result that arrives later is an orphan by the same rule that makes the call one.
    """
    orphan_uses = 0
    orphan_results = 0
    emptied: list[int] = []
    for index, message in enumerate(messages):
        following = messages[index + 1] if index + 1 < len(messages) else None
        answered = _ids_of(following, "tool_result", "tool_use_id") if _role(following) == "user" else set[str]()
        preceding = messages[index - 1] if index else None
        called = _ids_of(preceding, "tool_use", "id") if _role(preceding) == "assistant" else set[str]()

        before = _blocks(message)
        kept: list[Any] = []
        for block in before:
            entry = cast(dict[str, Any], block) if isinstance(block, dict) else None
            kind = entry.get("type") if entry is not None else None
            if entry is not None and kind == "tool_use" and _role(message) == "assistant":
                identifier = entry.get("id")
                if not isinstance(identifier, str) or identifier not in answered:
                    orphan_uses += 1
                    continue
            elif entry is not None and kind == "tool_result" and _role(message) == "user":
                identifier = entry.get("tool_use_id")
                if not isinstance(identifier, str) or identifier not in called:
                    orphan_results += 1
                    continue
            kept.append(block)
        if not isinstance(message, dict) or not isinstance(cast(dict[str, Any], message).get("content"), list):
            continue
        cast(dict[str, Any], message)["content"] = kept
        if before and not kept:
            emptied.append(index)

    dropped = _drop(messages, emptied)
    return orphan_uses, orphan_results, dropped


def _drop(messages: list[Any], indexes: list[int]) -> int:
    """Remove the named turns, unless that would leave the body with none.

    A request with no messages is a different request, not a repaired one — so in that one case the orphan travels and upstream says what is wrong with it.
    """
    if not indexes or len(indexes) == len(messages):
        return 0
    doomed = set(indexes)
    messages[:] = [message for index, message in enumerate(messages) if index not in doomed]
    return len(doomed)


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

    # Before the per-message passes below, because those read `content` and this decides which blocks are still in it. Unconditional and before translation: both endpoints refuse a broken pair, each in its own words, so this is not a property of either leg.
    orphan_uses, orphan_results, emptied = repair_tool_pairs(messages)
    if orphan_uses or orphan_results:
        # INFO rather than DEBUG: this removes a call the model made, or an answer it was given, and an operator wondering why a tool disappeared from the transcript should not have to turn on debug logging to find out. It is also not routine — a client that keeps its own history intact never produces one.
        logger.info(
            "repaired %d unanswered tool call(s) and %d unmatched tool result(s); %d turn(s) had nothing left",
            orphan_uses,
            orphan_results,
            emptied,
        )

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
