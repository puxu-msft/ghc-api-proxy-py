"""The `include` entry that asks a Responses upstream for encrypted reasoning, shaped per configuration.

**Passthrough by default, and the default is the whole point.** Encrypted reasoning is opt-in on the Responses wire — only a request whose `include` array names `reasoning.encrypted_content` gets the opaque seal back — and until this pass existed the proxy's behaviour was already split: a translated request composes no `include` at all, while a native request forwards whatever `include` the client wrote. `hook_fix_responses_request.reasoning_encrypted_include` names what happens instead; `passthrough` is that split behaviour, unchanged, because the default of a switch like this must not start asking an upstream for a payload kind nobody asked for.

**The two non-default values are opposite answers to the same question.** `always_add` guarantees the entry on every Responses-bound request — what cross-turn reasoning reuse needs on a `store: false` upstream, where the seal is the only way a previous turn's reasoning reaches the model again. `always_strip` guarantees its absence — the encrypted-reasoning off-switch; the upstream then returns summary text alone, which the reasoning-carrier contract already accepts as a reasoning source without a seal.

**Scoped to the Responses target, and only to a body this proxy can speak for.** An Anthropic Messages upstream has no `include` parameter, and a Chat Completions leg has neither, so the gate is the routed target format and nothing else. An `include` that arrived as something other than a list is left exactly as it stands — upstream is the authority on what it accepts, and reshaping a shape this proxy does not recognise is how a repair becomes a second defect; the pass logs what it declined instead of editing quietly.
"""

import logging
from typing import Any, cast

from app.config.schema import ReasoningEncryptedIncludePolicy
from app.pipeline.request import RequestContext, WireFormat

logger = logging.getLogger(__name__)

SUBSCRIBER_ID = "builtin:reasoning-encrypted-include"

# The includable that asks the upstream to seal reasoning. The one string the Responses wire defines for this, not a spelling this proxy chose.
REASONING_ENCRYPTED_CONTENT = "reasoning.encrypted_content"


async def shape_reasoning_encrypted_include(
    context: RequestContext,
    *,
    policy: ReasoningEncryptedIncludePolicy,
) -> None:
    """Add or strip `reasoning.encrypted_content` on the outbound body, per `policy`.

    `passthrough` returns before reading anything — the cheapest possible statement that this request's `include` is nobody here's business. Both edits fire at `attempt.prepare`, so a retry re-runs them over the body the last attempt's pass left; both are idempotent by construction.
    """
    if policy == "passthrough":
        return
    if context.target_format is not WireFormat.OPENAI_RESPONSES:
        return

    include = context.payload.get("include")
    if include is not None and not isinstance(include, list):
        logger.info(
            "include is %s, not a list; left untouched for upstream to judge",
            type(include).__name__,
        )
        return

    if policy == "always_add":
        if include is None:
            context.payload["include"] = [REASONING_ENCRYPTED_CONTENT]
            logger.info("added include %r to a request that carried none", REASONING_ENCRYPTED_CONTENT)
        elif REASONING_ENCRYPTED_CONTENT not in cast(list[Any], include):
            cast(list[Any], include).append(REASONING_ENCRYPTED_CONTENT)
            logger.info("added %r to the request's include", REASONING_ENCRYPTED_CONTENT)
        return

    # `always_strip`. The entry goes; an `include` left holding nothing goes with it — an empty array says something no reader of this wire expects, and after the strip it says nothing at all.
    if include is None:
        return
    entries = cast(list[Any], include)
    if REASONING_ENCRYPTED_CONTENT not in entries:
        return
    entries.remove(REASONING_ENCRYPTED_CONTENT)
    if not entries:
        del context.payload["include"]
    logger.info("stripped %r from the request's include", REASONING_ENCRYPTED_CONTENT)
