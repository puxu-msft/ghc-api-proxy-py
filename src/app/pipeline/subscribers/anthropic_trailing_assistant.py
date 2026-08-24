"""A conversation this proxy's own repairs left ending on an assistant turn.

Copilot's Anthropic Messages endpoint refuses one outright — measured 2026-08-24 against `claude-sonnet-5`, both with a string `content` and with a block array: `This model does not support assistant message prefill. The conversation must end with a user message.` The 400 is the whole request, and the client replays it on its next turn and is refused again.

**The request that earns it is one this proxy created.** Two passes here delete whole turns, and either can delete the last one:

- `repair_tool_pairs` (`pipeline/anthropic_request_hook.py`) drops a turn its orphan removal emptied. A final user turn carrying nothing but `tool_result` blocks whose calls are gone — after a client-side compaction, or after this proxy's own thinking-block strip — empties and goes.
- `drop_blank_text_blocks` (`pipeline/subscribers/blank_text.py`) drops a user turn whose only content was a blank text block.

Both were measured on a legal three-turn body ending in `user`, and both leave it ending in `assistant`. `repair_tool_pairs` had already asked what dropping a turn costs and answered one half of it — its own docstring records that two same-role turns in a row are accepted — but "the conversation now ends with an assistant turn" is the other half, and nothing had asked.

**A prefill the client wrote itself is left alone**, and that is the whole reason this reads `original_payload` rather than just the tail of `messages`. Prefill is a documented Anthropic feature; a client using it deliberately is asking for something this model no longer offers, and upstream's refusal says exactly that. Appending a turn there would hand back a perfectly good answer that silently ignored the constraint the client asked for — the client would have no way to learn its prefill did nothing. Repairing what *we* broke and reporting what the client asked for are different jobs.

**An assistant turn with `content: []` is not a prefill and is left alone too.** Measured in this repository on 2026-08-20 (`exp/260820-empty-text-probe/`, F4 and F6): upstream answers 200 to one, last or mid-conversation. The first draft of this module asserted "must not end on an assistant turn" as a flat rule and would have injected a user instruction into a request that already worked — and into exactly the shape its neighbour `drop_blank_text_blocks` produces, since that pass empties an assistant turn rather than dropping it. Two measured 400s made a rule that a third measured 200 already contradicted.

Spec: `.dev/docs/anthropic-direct-request-shape/spec.md` §6.
"""

import logging
from collections.abc import Mapping
from typing import Any, cast

from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.translation_driver.semantic import Loss, LossCode

logger = logging.getLogger(__name__)

SUBSCRIBER_ID = "builtin:anthropic-trailing-assistant"

# The first-party client's own wording for this repair (`vscode-copilot-chat`, `platform/endpoint/node/messagesApi.ts`), which hits the same guard from the other side — its upstream code can drop a trailing user turn too. Copied rather than invented because a synthetic prompt is text the model will read, and there is no reason to write a second one when a shipped client has already chosen its words.
SYNTHETIC_TEXT = "Please continue."

_REQUEST_LOSSES = "conversion_losses"


def _last_message(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """The final message, or `None` when there is no readable one."""
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return None
    last = cast(list[Any], messages)[-1]
    return cast(dict[str, Any], last) if isinstance(last, dict) else None


def _last_role(payload: Mapping[str, Any]) -> str | None:
    """The role of the final message, or `None` when there is no readable one.

    `None` covers two cases that must lead to the same decision here: a body with no `messages` at all — which is what a `/responses` request's `original_payload` looks like — and one whose tail is malformed. Neither says what the client meant, and this module never injects text on a guess.
    """
    last = _last_message(payload)
    if last is None:
        return None
    role = last.get("role")
    return role if isinstance(role, str) else None


def _is_empty_content(message: Mapping[str, Any]) -> bool:
    """Whether this turn carries an empty block list — a turn with nothing in it to continue.

    Measured in this repository on 2026-08-20 (`exp/260820-empty-text-probe/`, F4 and F6): a final assistant turn with `content: []` answers **200** on `claude-sonnet-5`, and so does one mid-conversation. It is not a prefill, because there is nothing to prefill with. `drop_blank_text_blocks` produces exactly this shape — it empties an assistant turn rather than dropping it — so without this test the two passes would fight, and the second would inject a user instruction into a request that was already fine.

    Only the empty *list* is treated this way, which is the shape that was measured. `content: ""` is left to the prefill branch: nothing has measured it, and the measured 400s were both non-empty content.
    """
    content = message.get("content")
    return isinstance(content, list) and not cast(list[Any], content)


async def repair_trailing_assistant(context: RequestContext) -> None:
    """Give the conversation a user turn to end on, when this proxy is why it lacks one.

    Registered **after** `builtin:blank-text-blocks` by an explicit constraint rather than by convention: that pass is the last thing on this event that can remove a message, and a guard that ran before it would check a message list that is not the one going out.

    Runs on the counting leg too, and must: `handle_count_tokens` exists to measure the body that would actually be sent, and a count taken one turn short of it measures a different request. Nothing here refuses anything, so there is nothing for counting to be exempt from.

    Idempotent by construction — after it runs the conversation ends on a user turn, which is the branch that returns.

    **Three separate ways it declines, and each is a different fact.** The tail is not an assistant turn; the tail is an assistant turn with nothing in it, which upstream accepts; or the client's own body ended that way. Collapsing any of them into "check the tail role" is what put text the client never wrote into two shapes that did not need it.
    """
    if context.target_format is not WireFormat.ANTHROPIC_MESSAGES:
        return
    tail = _last_message(context.payload)
    if tail is None or tail.get("role") != "assistant":
        return
    if _is_empty_content(tail):
        # Measured 200. Nothing to repair, and repairing would add a turn to a request that works.
        return

    client_tail = _last_role(context.original_payload)
    if client_tail != "user":
        # Everything that is not a positive "the client ended on a user turn" declines, and the direction is deliberate: this module may only ever add text on evidence that the client's own conversation did *not* end here.
        #
        # `assistant` is the client's own prefill. Upstream names it precisely and that answer is the one the client needs; a repair here would look like success while silently dropping the constraint the client asked for.
        #
        # `None` is a body this cannot compare — most importantly a `/responses` request, whose original has `input` rather than `messages`. That leaves a real gap: `drop_blank_text_blocks` runs on translated-to-Anthropic bodies too, so a translated conversation can lose its final user turn and go out unrepaired. It is left as a gap knowingly, because the alternative is guessing across a protocol boundary, and the failure modes are not comparable — an unrepaired body earns a 400 that says exactly what is wrong, while a wrong guess puts a sentence the client never wrote in front of the model and reports success. Spec §6.5.
        return

    messages = cast(list[Any], context.payload["messages"])
    messages.append({"role": "user", "content": [{"type": "text", "text": SYNTHETIC_TEXT}]})

    detail = f"conversation ended on an assistant turn after this proxy's repairs; appended {SYNTHETIC_TEXT!r}"
    recorded = context.extras.get(_REQUEST_LOSSES)
    if not isinstance(recorded, list):
        recorded = []
        context.extras[_REQUEST_LOSSES] = recorded
    cast(list[Any], recorded).append(Loss(LossCode.SYNTHETIC_TURN_ADDED, detail))

    # INFO rather than debug: it changes what the model is shown, which is not something to bury — and it is also the only signal that an earlier repair took the client's last turn.
    logger.info("appended a synthetic user turn for %r: %s", context.resolved_model, detail)
