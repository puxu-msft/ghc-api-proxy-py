"""Text blocks carrying no text, removed from the body the Anthropic Messages endpoint is about to receive.

A text block whose text is empty or only whitespace says nothing, and Copilot's Anthropic Messages endpoint refuses the whole request over one — `messages: text content blocks must be non-empty`, and for whitespace `text content blocks must contain non-whitespace text`. One block the client never meant to send costs the entire turn, and the client replays it on its next request and is refused again. Production hit this twice in a row on 2026-08-20 with `claude-opus-5`.

Where the block came from is settled and is not this module's problem any more: `stream.py` used to synthesise a placeholder text block when upstream had produced nothing for 240 seconds, the client stored it as part of that turn, and the turn came back. That producer is gone. This is the other half — the guard that catches such a block whoever produced it, including a client that arrives carrying one from an older session. One exception, and it is measured rather than assumed: a *user* turn whose content is nothing but blank blocks is sent as it arrived, because every rewrite of it is refused too. See the bottom of this file.

**Scoped to the Anthropic leg, and measured rather than assumed.** `exp/260820-empty-text-probe/` asked the live upstream directly: on `gpt-5.5`, non-streaming, `/responses` answers 200 to an empty `input_text`, to a whitespace-only one, and to an assistant turn whose `output_text` is empty, while `/v1/messages` answers 400 to the empty block in the same run with the same credentials. So the Responses leg tolerates the shape and is left alone — this runs at `attempt.prepare` and reads the routed endpoint, which is the last point at which the question "who is going to read this" has an answer. The qualifiers matter: that same run shows two endpoints on one host disagreeing about a body, so "same endpoint, same verdict" is an extrapolation for other models rather than something the probe established. The exposure is small — no Claude model on this upstream advertises `/responses` at all.

**Why not earlier.** An earlier revision did this before translation, where the body is still Anthropic-shaped for both legs. That put the rewrite on the primary path to satisfy a rule only the other path has, which the probe above showed to be unnecessary. Format repair belongs where the format is going, not where it happened to arrive.
"""

import logging
from collections.abc import Mapping
from typing import Any, cast

from app.anthropic.thinking.destack import SYNTHETIC_SEPARATOR
from app.anthropic.thinking.protection import THINKING_TYPES
from app.pipeline.request import RequestContext, WireFormat

logger = logging.getLogger(__name__)

SUBSCRIBER_ID = "builtin:blank-text-blocks"


def _is_blank_text(block: Any) -> bool:
    """Whether this block carries no text at all.

    That is the whole criterion, and it is a property of the block rather than of whoever receives it. `.strip()` rather than `== ""` because whitespace is not text either, which is why upstream refuses the two separately and in different words.

    A missing or null `text` counts as blank. A `text` that is not a string does not: this removes blocks that carry nothing, and quietly deleting a malformed one would hide a client bug behind a rewrite instead of letting upstream name it.
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


def _is_thinking(block: Any) -> bool:
    return isinstance(block, Mapping) and cast(Mapping[str, Any], block).get("type") in THINKING_TYPES


def _without_blank_text(content: list[Any]) -> list[Any]:
    """The same blocks, minus the ones that say nothing.

    Returns the argument itself when nothing matched, so an untouched body stays the object it arrived as and the caller can tell "nothing to do" from "everything went" by identity.

    One blank block is not simply dropped: the one standing between two thinking blocks is replaced by the separator `destack_content` would have used. Removing it outright would leave the two thinking blocks adjacent, which is the arrangement the layout pass exists to prevent — and that pass ran before translation, long before this one, so it cannot clean up after this. This is reasoning about a shape rather than a measurement of one: it has not been observed in production, but it costs one comparison and the alternative is trading one refusal for another.
    """
    kept: list[Any] = []
    changed = False
    for index, block in enumerate(content):
        if not _is_blank_text(block):
            kept.append(block)
            continue
        changed = True
        following = next(
            (later for later in content[index + 1 :] if not _is_blank_text(later)), None
        )
        if kept and _is_thinking(kept[-1]) and _is_thinking(following):
            kept.append({"type": "text", "text": SYNTHETIC_SEPARATOR})
    return content if not changed else kept


async def drop_blank_text_blocks(context: RequestContext) -> None:
    """Remove blocks that say nothing from the body this attempt is about to send.

    Reads the routed endpoint rather than the inbound format, for the same reason `adapt_server_tools` does: what upstream accepts is a property of the endpoint being spoken to. A request that arrived in another protocol and was translated *into* Anthropic shape is refused over a blank block just the same.
    """
    if context.target_format is not WireFormat.ANTHROPIC_MESSAGES:
        return
    payload = context.payload

    system_value = payload.get("system")
    if isinstance(system_value, list):
        system = cast(list[Any], system_value)
        kept = _without_blank_text(system)
        if kept is not system:
            if kept:
                payload["system"] = kept
                logger.debug("dropped %d blank block(s) from system", len(system) - len(kept))
            else:
                # A system prompt made of nothing but blank blocks says exactly as much as no system prompt, and a body with no `system` at all is unremarkable to this upstream. `system: []` is a third thing neither of us has asked it about, so it is not the one to send.
                del payload["system"]
                logger.debug("system carried nothing but blank blocks; the field is gone rather than empty")

    messages_value = payload.get("messages")
    if not isinstance(messages_value, list):
        return
    messages = cast(list[Any], messages_value)
    doomed: list[int] = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        entry = cast(dict[str, Any], message)
        content_value = entry.get("content")
        if not isinstance(content_value, list):
            continue
        content = cast(list[Any], content_value)
        kept = _without_blank_text(content)
        if kept is content:
            continue
        if kept:
            logger.debug("dropped %d blank block(s) from a message", len(content) - len(kept))
            entry["content"] = kept
            continue
        if entry.get("role") == "assistant":
            # An assistant turn that said nothing is allowed to say nothing: `content: []` is accepted here, measured on 2026-08-20 both mid-conversation and as the final turn (`exp/260820-empty-text-probe/`, F6 and F4, 200 each), while the blank block it replaces is refused (F3, 400). The two spellings mean the same and only one of them travels, so this is the rewrite the `system` branch gets for the same reason.
            logger.debug("a message carried nothing but blank text blocks; emptying the assistant turn, which upstream accepts")
            entry["content"] = []
            continue
        # A user turn has no such spelling: `content: []` is refused too, and in its own words — `messages.0: user messages must have non-empty content` (F1, 400) beside the blank block's `text content blocks must be non-empty` (F2, 400). So the turn goes rather than its content.
        # This used to travel unchanged, on the grounds that dropping a turn puts two same-role turns next to each other and that had not been measured. It has since: `exp/260820-tool-pair-probe/` G4 sends two assistant turns in a row and gets 200. The same reasoning now runs the other way — a turn saying nothing is worth less than the request it was costing.
        doomed.append(index)

    if doomed and len(doomed) < len(messages):
        logger.info("dropped %d turn(s) carrying nothing but blank text blocks", len(doomed))
        gone = set(doomed)
        messages[:] = [message for index, message in enumerate(messages) if index not in gone]
    elif doomed:
        # Every turn would go. A request with no messages is a different request, not a repaired one, so the body travels as it came and upstream says what is wrong with it.
        logger.warning("every turn carries nothing but blank text blocks; the body is being sent unchanged")
