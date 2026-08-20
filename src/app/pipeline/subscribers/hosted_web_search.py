"""Hosted web search, withheld from models that do not run it.

The Responses endpoint executes web search itself, and the request translator turns the client's Anthropic declaration into the `{"type": "web_search"}` that endpoint answers to. Whether the model behind it *actually runs* the search is a separate question, and the catalog cannot answer it: measured 2026-08-20 over the live catalog, no model advertises a web-search capability bit under any name, and the two models known to work are indistinguishable from the rest on every advertised field. So the answer is a list an operator maintains — `model_providers.<name>.models_support_web_search`.

**Why this is a subscriber and not part of the translation.** The translator is handed a `SemanticRequest`, whose `model` is the name the *client* asked for; the gate has to read the *resolved* model, which only exists once routing has run. `attempt.prepare` is the first point where both that and the body about to be sent are available — the same reason `builtin:server-tool-capability` lives here.

**Why it removes rather than refuses.** A model that cannot search is not a malformed request, and failing the turn would take the conversation with it. Removing the declaration costs the capability and keeps the turn, which is the trade the Anthropic leg already makes for the same reason. It is reported at INFO with the model named, because the failure mode this guards against — a client that believes it is searching and is not — is otherwise invisible.
"""

import logging
from typing import Any, cast

from app.pipeline.request import RequestContext, WireFormat

logger = logging.getLogger(__name__)

SUBSCRIBER_ID = "builtin:hosted-web-search-gate"

# The spelling the translator emits, and the only one this removes. A client that sent a Responses
# request naming a builtin directly is left alone: it asked this endpoint for its own feature in
# its own words, and second-guessing that is not what a capability gate is for.
_HOSTED_WEB_SEARCH = "web_search"


def _is_hosted_web_search(tool: Any) -> bool:
    if not isinstance(tool, dict):
        return False
    return cast(dict[str, Any], tool).get("type") == _HOSTED_WEB_SEARCH


def _drop_hosted_choice(payload: dict[str, Any]) -> None:
    """Remove a `tool_choice` that demanded the search now being withheld.

    `{"type": "web_search"}` in the choice position names a tool that is no longer declared, and upstream refuses that on its own — so leaving it would trade a missing capability for a failed turn, which is the opposite of what removing the declaration is for.
    """
    choice = payload.get("tool_choice")
    if isinstance(choice, dict) and cast(dict[str, Any], choice).get("type") == _HOSTED_WEB_SEARCH:
        del payload["tool_choice"]
        return
    if not payload.get("tools"):
        # Nothing left to choose from at all; the field is only accepted alongside a non-empty list.
        payload.pop("tool_choice", None)


async def gate_hosted_web_search(context: RequestContext, supported: frozenset[str]) -> None:
    """Withhold hosted web search from a model not known to run it."""
    if context.target_format is not WireFormat.OPENAI_RESPONSES:
        return
    if context.resolved_model in supported:
        return
    payload = context.payload
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return
    kept = [tool for tool in cast(list[Any], tools) if not _is_hosted_web_search(tool)]
    if len(kept) == len(cast(list[Any], tools)):
        return

    if kept:
        payload["tools"] = kept
    else:
        # Absent rather than `[]`, which is the spelling every request without tools already uses.
        del payload["tools"]
    _drop_hosted_choice(payload)

    # INFO, and naming the model: this is the one place an operator can find out that a search the
    # client asked for is not going to happen. The alternative — a model that quietly answers from
    # memory while the client believes it searched — is the failure this exists to make visible.
    logger.info(
        "withheld hosted web search from %r: it is not in models_support_web_search, so the model will answer without searching",
        context.resolved_model,
    )
