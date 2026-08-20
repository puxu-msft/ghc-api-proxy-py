"""Hosted web search, refused for models that do not run it.

The Responses endpoint executes web search itself, and the request translator turns the client's Anthropic declaration into the `{"type": "web_search"}` that endpoint answers to. Whether the model behind it *actually runs* the search is a separate question, and the catalog cannot answer it: measured 2026-08-20 over the live catalog, no model advertises a web-search capability bit under any name, and the two models known to work are indistinguishable from the rest on every advertised field. So the answer is a list an operator maintains — `model_providers.<name>.models_support_web_search`.

**Why this is a subscriber and not part of the translation.** The translator is handed a `SemanticRequest`, whose `model` is the name the *client* asked for; the gate has to read the *resolved* model, which only exists once routing has run. `attempt.prepare` is the first point where both that and the body about to be sent are available.

**Why it refuses rather than removing the declaration, which is what it used to do.** Removing it looks like the gentler option — the turn survives, one capability short — and on this client it is the dangerous one. Claude Code runs web search as a separate sub-request whose entire content is `Perform a web search for the query: X` and whose `tools` array holds nothing else; measured over 190 real ones, every single time. A sub-request stripped of its only tool does not fail. The model answers from memory, and the client renders whatever comes back under a `Web search results for query:` heading it attaches unconditionally — no `is_error`, no marker of any kind. Remembered text arrives labelled as searched fact.

So this raises instead, and `handle()` answers it: the reply becomes a `server_tool_use` paired with a `web_search_tool_result` carrying a single error object, which is the shape Anthropic defines for a search that did not run. Not an HTTP error — the same transcript that shows the model degrading well on a 400 also shows the client retrying it three times first, because an HTTP error reads as a transport fault. A failed tool does not get retried. See `delivery/synthetic.py`.
"""

import logging
from typing import Any, cast

from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.subscribers.counting import COUNTING_ONLY
from app.pipeline.translation_driver.semantic import WebSearchNotExecutable

logger = logging.getLogger(__name__)

SUBSCRIBER_ID = "builtin:hosted-web-search-gate"

# The spelling the translator emits, and the only one this reads. A client that sent a Responses
# request naming a builtin directly is left alone: it asked this endpoint for its own feature in
# its own words, and second-guessing that is not what a capability gate is for.
_HOSTED_WEB_SEARCH = "web_search"


def _is_hosted_web_search(tool: Any) -> bool:
    if not isinstance(tool, dict):
        return False
    return cast(dict[str, Any], tool).get("type") == _HOSTED_WEB_SEARCH


async def gate_hosted_web_search(context: RequestContext, supported: frozenset[str]) -> None:
    """Stop a search that this model is not known to run, so it is answered rather than invented."""
    if context.target_format is not WireFormat.OPENAI_RESPONSES:
        return
    if context.extras.get(COUNTING_ONLY):
        # Measuring, not sending: no reply exists to be invented, so there is nothing to refuse for.
        return
    if context.resolved_model in supported:
        return
    tools = context.payload.get("tools")
    if not isinstance(tools, list):
        return
    if not any(_is_hosted_web_search(tool) for tool in cast(list[Any], tools)):
        return

    # Named at INFO before the refusal, because the error reaches the client and this reaches the
    # operator — and it is the operator who can fix it, by adding the model to the list or finding
    # out that it does not belong there.
    logger.info(
        "answering a web search for %r as failed: it is not in models_support_web_search",
        context.resolved_model,
    )
    raise WebSearchNotExecutable(
        f"{context.resolved_model} is not configured to run hosted web search; add it to"
        " models_support_web_search if it does",
        code="server_tool_capability_unavailable",
        field_path="tools.web_search",
    )
