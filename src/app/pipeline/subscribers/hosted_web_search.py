"""Hosted web search, refused for models that do not run it.

The Responses endpoint executes web search itself, and the request translator turns the client's Anthropic declaration into the `{"type": "web_search"}` that endpoint answers to. Whether the model behind it *actually runs* the search is a separate question, and the catalog cannot answer it: measured 2026-08-20 over the live catalog, no model advertises a web-search capability bit under any name, and the two models known to work are indistinguishable from the rest on every advertised field. So the answer is a list an operator maintains — `model_providers.<name>.models_support_web_search`.

**The entries are regular expressions, ruled 2026-08-21.** A list of exact ids has to be edited every time the catalog gains a model, and the edit is the kind nobody makes until a search has already been answered as failed for a model that could have run it. A pattern covers the version family instead, so the next `gpt-5.7` is claimed on arrival. It stays a list rather than becoming a name-derived predicate — which is what a third-party patch of the official extension does, keying on `gpt` major version ≥ 5 — because the vendor split is not visible in the name: `gpt-5-mini` is Azure OpenAI, a different supply chain from the `gpt-5.N` line, and a predicate broad enough to be useful sweeps it in. An operator who knows better than the default can say so; a predicate compiled into the binary cannot be told.

**Why this is a subscriber and not part of the translation.** The translator is handed a `SemanticRequest`, whose `model` is the name the *client* asked for; the gate has to read the *resolved* model, which only exists once routing has run. `attempt.prepare` is the first point where both that and the body about to be sent are available.

**Why it refuses rather than removing the declaration, which is what it used to do.** Removing it looks like the gentler option — the turn survives, one capability short — and on this client it is the dangerous one. Claude Code runs web search as a separate sub-request whose entire content is `Perform a web search for the query: X` and whose `tools` array holds nothing else; measured over 190 real ones, every single time. A sub-request stripped of its only tool does not fail. The model answers from memory, and the client renders whatever comes back under a `Web search results for query:` heading it attaches unconditionally — no `is_error`, no marker of any kind. Remembered text arrives labelled as searched fact.

So this raises instead, and `handle()` answers it: the reply becomes a `server_tool_use` paired with a `web_search_tool_result` carrying a single error object, which is the shape Anthropic defines for a search that did not run. Not an HTTP error — the same transcript that shows the model degrading well on a 400 also shows the client retrying it three times first, because an HTTP error reads as a transport fault. A failed tool does not get retried. See `delivery/synthetic.py`.
"""

import logging
import re
from collections.abc import Iterable, Sequence
from typing import Any, cast

from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.subscribers.counting import COUNTING_ONLY
from app.pipeline.translation_driver.semantic import WebSearchNotExecutable

logger = logging.getLogger(__name__)

SUBSCRIBER_ID = "builtin:hosted-web-search-gate"

# The spelling the translator emits, and the only one this reads. A client that sent a Responses request naming a builtin directly is left alone: it asked this endpoint for its own feature in its own words, and second-guessing that is not what a capability gate is for.
_HOSTED_WEB_SEARCH = "web_search"


def compile_supported(patterns: Iterable[str]) -> tuple[re.Pattern[str], ...]:
    """Compile the configured entries once, at startup, so a bad one is a startup failure.

    Left uncompiled they would be compiled per request, and a pattern that does not compile would raise from inside a request rather than from the config that holds it. Worse, catching that per request would turn a typo into a model that silently never matches — the gate would answer every search as failed and name a model that is in fact listed.

    Anchored by using `fullmatch` at the call site rather than by wrapping each pattern in `\\A…\\Z` here: an entry written as a plain model id (`gpt-5.5`), which is what this key held before it took patterns, then keeps meaning what its author meant. A wrapper would also have to reason about alternation — `a|b` wrapped naively binds the anchors to one branch each.

    A pattern that does not compile is re-raised naming itself and the key it came from. `re`'s own message says only what is wrong and at which character offset, which for a list of several entries leaves the operator to work out *which* entry the offset belongs to.
    """
    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern))
        except re.error as exc:
            raise ValueError(
                f"models_support_web_search entry {pattern!r} is not a valid regular expression: {exc}"
            ) from exc
    return tuple(compiled)


def _is_hosted_web_search(tool: Any) -> bool:
    if not isinstance(tool, dict):
        return False
    return cast(dict[str, Any], tool).get("type") == _HOSTED_WEB_SEARCH


def _is_supported(model: str, supported: Sequence[re.Pattern[str]]) -> bool:
    """Whether any configured pattern claims this model.

    `fullmatch`, not `search`: a list of model ids is what an operator writes here, and under `search` the entry `gpt-5.5` would also claim `gpt-5.5-nonsense` — silently widening a list whose whole purpose is to say which models were checked.
    """
    return any(pattern.fullmatch(model) for pattern in supported)


async def gate_hosted_web_search(
    context: RequestContext, supported: Sequence[re.Pattern[str]]
) -> None:
    """Stop a search that this model is not known to run, so it is answered rather than invented."""
    if context.target_format is not WireFormat.OPENAI_RESPONSES:
        return
    if context.extras.get(COUNTING_ONLY):
        # Measuring, not sending: no reply exists to be invented, so there is nothing to refuse for.
        return
    if _is_supported(context.resolved_model, supported):
        return
    tools = context.payload.get("tools")
    if not isinstance(tools, list):
        return
    if not any(_is_hosted_web_search(tool) for tool in cast(list[Any], tools)):
        return

    # Named at INFO before the refusal, because the error reaches the client and this reaches the operator — and it is the operator who can fix it, by adding the model to the list or finding out that it does not belong there.
    logger.info(
        "answering a web search for %r as failed: no models_support_web_search pattern matches it",
        context.resolved_model,
    )
    raise WebSearchNotExecutable(
        f"{context.resolved_model} is not configured to run hosted web search; add a"
        " models_support_web_search pattern matching it if it does",
        code="server_tool_capability_unavailable",
        field_path="tools.web_search",
    )
