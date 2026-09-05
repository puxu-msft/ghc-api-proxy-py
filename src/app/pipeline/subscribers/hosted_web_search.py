"""Hosted web search, refused unless it is turned on and the model is known to run it.

**Off by default, ruled 2026-08-21.** The Responses endpoint really does execute a search — measured — and the response crossing restores the native `server_tool_use` / `web_search_tool_result` pair. The support remains partial: Responses supplies no genuine Anthropic `encrypted_content`, so the structured result is reported as unavailable while the model's answer remains text; `max_uses` and the domain lists cannot be sent. `model_translation.to_openai_responses.hosted_web_search` is the switch, and leaving it off keeps that partial feature from becoming what every request gets.

The request translator turns the client's Anthropic declaration into the `{"type": "web_search"}` that endpoint answers to. Whether the model behind it *actually runs* the search is a separate question, and the catalog cannot answer it: measured 2026-08-20 over the live catalog, no model advertises a web-search capability bit under any name, and the two models known to work are indistinguishable from the rest on every advertised field. So the answer is a list an operator maintains — `model_providers.<name>.models_support_web_search`.

**The entries are regular expressions, ruled 2026-08-21.** A list of exact ids has to be edited every time the catalog gains a model, and the edit is the kind nobody makes until a search has already been answered as failed for a model that could have run it. A pattern covers the version family instead, so the next `gpt-5.7` is claimed on arrival. It stays a list rather than becoming a name-derived predicate — which is what a third-party patch of the official extension does, keying on `gpt` major version ≥ 5 — because the vendor split is not visible in the name: `gpt-5-mini` is Azure OpenAI, a different supply chain from the `gpt-5.N` line, and a predicate broad enough to be useful sweeps it in. An operator who knows better than the default can say so; a predicate compiled into the binary cannot be told.

**Why this is a subscriber and not part of the translation.** The translator is handed a `SemanticRequest`, whose `model` is the name the *client* asked for; the gate has to read the *resolved* model, which only exists once routing has run. `attempt.prepare` is the first point where both that and the body about to be sent are available.

**Why it refuses rather than removing the declaration, which is what it used to do.** Removing it looks like the gentler option — the turn survives, one capability short — and on this client it is the dangerous one. Claude Code runs web search as a separate sub-request whose entire content is `Perform a web search for the query: X` and whose `tools` array holds nothing else; measured over 190 real ones, every single time. A sub-request stripped of its only tool does not fail. The model answers from memory, and the client renders whatever comes back under a `Web search results for query:` heading it attaches unconditionally — no `is_error`, no marker of any kind. Remembered text arrives labelled as searched fact.

So this raises instead, and `handle()` answers it: the reply becomes a `server_tool_use` paired with a `web_search_tool_result` carrying a single error object, which is the shape Anthropic defines for a search that did not run. Not an HTTP error — the same transcript that shows the model degrading well on a 400 also shows three attempts before it did. **Those three are the model calling `WebSearch` again, not the transport retrying**: the client's retry table does not retry a 400 at all, and reserves retries for 408, 409, 401, 5xx and usually 429 — ten by default, more if configured. Corrected 2026-08-30; the trade is unchanged, its mechanism was misnamed. What the failed tool buys is that no *mechanism* repeats it; whether the model does anyway is unmeasured. See `delivery/synthetic.py`.
"""

import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, cast

from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.subscribers.counting import COUNTING_ONLY
from app.pipeline.translation_driver.semantic import WebSearchNotExecutable

logger = logging.getLogger(__name__)

SUBSCRIBER_ID = "builtin:hosted-web-search-gate"

# The spelling the translator emits — and **the same tool object a Responses client writes for itself**, which is what makes it useless for deciding which requests this gate owns. The comment here used to claim the opposite ("the only one this reads. A client that sent a Responses request naming a builtin directly is left alone"), and the gate was written on that belief; the two are the same spelling, so it judged the direct client too. Issue #1. Which crossing this gate owns is decided in `gate_hosted_web_search` by the inbound format, where the answer is knowable.
_HOSTED_WEB_SEARCH = "web_search"


def compile_supported(patterns: Iterable[str]) -> tuple[re.Pattern[str], ...]:
    """Compile one provider's entries once, at startup, so a bad one is a startup failure.

    Left uncompiled they would be compiled per request, and a pattern that does not compile would raise from inside a request rather than from the config that holds it. Worse, catching that per request would turn a typo into a model that silently never matches — the gate would answer every search as failed and name a model that is in fact listed.

    Anchored by using `fullmatch` at the call site rather than by wrapping each pattern in `\\A…\\Z` here, which would have to reason about alternation: `a|b` wrapped naively binds one anchor to each branch.

    **An entry is a regular expression, including the ones that look like plain model ids.** This docstring used to promise that `gpt-5.5` "keeps meaning what its author meant"; it does not, because `.` is a wildcard, and `re.fullmatch("gpt-5.5", "gpt-5x5")` is true. Model ids in this catalog are full of dots, so that is the likely spelling for someone pinning one model — and the over-match sends an unvetted model's search upstream. To pin an id exactly, escape it: `gpt-5\\.5`.

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


def compile_supported_by_provider(
    providers: Mapping[str, Iterable[str]],
) -> dict[str, tuple[re.Pattern[str], ...]]:
    """Each provider's own list, kept apart.

    Merging them into one set was wrong, and the comment that justified it — model ids are unique across the catalog, so there is nothing to disambiguate — answers a question nobody asked. Uniqueness of the *id* says nothing about whether two providers **run** that model the same way, and the key lives under `model_providers.<name>` precisely because the answer is the provider's. Under a merge, a provider whose list is empty inherits every other provider's, so a request routed to it passes a gate its own configuration never opened.
    """
    return {name: compile_supported(patterns) for name, patterns in providers.items()}


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
    context: RequestContext,
    supported: Mapping[str, Sequence[re.Pattern[str]]],
    *,
    enabled: bool = False,
    default_provider: str = "",
) -> None:
    """Stop a search that will not run, so it is answered rather than invented.

    Two reasons it will not run, kept apart all the way to the log line. `model_translation.to_openai_responses.hosted_web_search` being off is a decision nobody has revisited; a model no pattern claims is a list that needs a line. They call for different actions from whoever reads the log, and collapsing them — by expressing "off" as an empty pattern list, say — would make the more likely of the two invisible, because the default *is* off and an operator who never set the key would be told their model is unlisted.

    The patterns are looked up **by the provider serving this request**, matching where the key lives in the config. `context.provider_name` is written by `apply_route` (`pipeline/routing.py`) as soon as routing decides, which is before any attempt begins. The `or default_provider` below is therefore unreachable on a routed request and is kept as a fail-closed floor rather than as a live branch. A provider name with no entry gets an empty tuple and so refuses — the direction that does not hand an unconfigured provider somebody else's permissions.

    Defaulting the keyword to `False` rather than `True` so a caller that forgets it refuses rather than searches: the wrong answer is then a search that did not happen and says so, not one that ran when nobody had asked for the feature.
    """
    if context.inbound_format is not WireFormat.ANTHROPIC_MESSAGES:
        # **This gate owns one crossing — Anthropic Messages in, Responses upstream — and the inbound format is what says whether a request is on it.** `model_translation.to_openai_responses.hosted_web_search` governs that crossing's translation: it decides whether an Anthropic `web_search_20250305` becomes the `{"type": "web_search"}` this endpoint answers to. A request that arrived on `/responses` wrote that object itself, in the upstream's own vocabulary, and there is nothing translated about it to switch off — it asked this endpoint for its own feature in its own words, which is not what a capability gate is for. Its fate belongs to that endpoint's own upstream contract. `hosted-web-search-spec.md` §1 scopes the whole feature the same way, and §9.0 now requires this predicate.
        #
        # Read off `inbound_format` and not off the tool object, which is where this went wrong: the translator emits the client's own spelling, so the payload cannot say which crossing a request is on. Judging the direct client anyway refused it, and the refusal was answered with an Anthropic `server_tool_use` / `web_search_tool_result` pair that the Responses framer has no item shape for — a `ValueError` that tore the stream after a 200 was already on the wire. Issue #1, reproduced by `test_a_direct_responses_client_declares_hosted_web_search_for_itself`.
        #
        # **What this predicate does not prove is who wrote the declaration**, and the first version of this comment claimed it did. Nothing here can: an Anthropic inbound may carry a Responses-shaped `{"type": "web_search"}` of its own, the translator keeps it, and this gate judges it. That input's handling on the Anthropic endpoint is undecided and is deliberately not settled here — `hosted-web-search-spec.md` §9.0 records it as such.
        #
        # Anthropic Messages by name rather than "was translated", because the emitter is one specific translator and naming it is what a later reader can check. A third inbound leg that learned to emit a hosted search would have to be added here, and that edit is the point.
        return
    if context.target_format is not WireFormat.OPENAI_RESPONSES:
        return
    if context.extras.get(COUNTING_ONLY):
        # Measuring, not sending: no reply exists to be invented, so there is nothing to refuse for.
        return
    patterns = supported.get(context.provider_name or default_provider, ())
    if enabled and _is_supported(context.resolved_model, patterns):
        return
    tools = context.payload.get("tools")
    if not isinstance(tools, list):
        return
    if not any(_is_hosted_web_search(tool) for tool in cast(list[Any], tools)):
        return

    # Named at INFO before the refusal, because the error reaches the client and this reaches the operator — and it is the operator who can fix it, by turning the feature on, adding a pattern, or finding out that this model does not belong there.
    if not enabled:
        logger.info(
            "answering a web search for %r as failed: hosted web search is off"
            " (model_translation.to_openai_responses.hosted_web_search)",
            context.resolved_model,
        )
        raise WebSearchNotExecutable(
            "hosted web search is not enabled on this proxy; set"
            " model_translation.to_openai_responses.hosted_web_search to turn it on",
            code="server_tool_disabled",
            field_path="tools.web_search",
        )
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
