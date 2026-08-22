"""The single owner of a request's life: route it, send it, and hand back what came.

Split out of `app.server.handler` on 2026-08-22. `docs/.human-controlled/request-pipeline.md` gives `app.pipeline` the driving and `app.server` the inbound HTTP surface, and the driving had grown inside the surface. `D-ARCH = B` says the same thing from the other side: one owner for approval, attempt, retry, transport exchange and finalize, and nothing else starting a second request lifecycle.

What is *not* here is deliberate. Rendering a failure as HTTP belongs to the edge (`app.server.http_errors`), reading a finished reply back in the client's vocabulary is `app.pipeline.reply`, and choosing a framer or an assembler is `app.pipeline.delivery_policy`.
"""

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

import httpx2
from pydantic import ValidationError

from app.core.chain import Chain
from app.model_provider import ModelProvider
from app.models.anthropic import MessagesRequest
from app.observability.metrics import BETA_FLAGS_STRIPPED
from app.pipeline.anthropic_request_hook import fix_anthropic_request
from app.pipeline.count_tokens import count_tokens
from app.pipeline.delivery.formats.anthropic_messages_synthetic_reply import (
    failed_search_body,
    failed_search_sse,
    query_from_request,
)
from app.pipeline.direct_driver import (
    DRIVERS,
    EVENT_ATTEMPT_PREPARE,
    DriverOutcome,
    LedgerBudget,
)
from app.pipeline.exceptions import (
    UpstreamTimeout,
)
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.request_headers import apply_path_header_policy, strip_denied_beta_flags
from app.pipeline.retry import RetryLedger
from app.pipeline.routing import Route, apply_route, decide_route, translation_target
from app.pipeline.subscribers.counting import COUNTING_ONLY
from app.pipeline.translation_driver.semantic import (
    WebSearchNotExecutable,
)
from app.tokenization.estimators import estimate_anthropic_input, estimate_responses_input
from app.wire_json import dumps


@dataclass(slots=True)
class HandledRequest:
    context: RequestContext
    route: Route
    outcome: DriverOutcome
    # Written by this proxy rather than by an upstream. The route still names whichever upstream would have answered — that is what the console line reports — so the reply's own dialect has to be carried separately, or `dialect_for` would try to read Anthropic blocks with the
    # Responses assembler.
    synthesized: bool = False

    @property
    def response(self) -> httpx2.Response | None:
        return self.outcome.response

def ledger_for(context: RequestContext, chain: Chain) -> RetryLedger:
    """One budget for the whole client request, built on first use and kept on the request.

    It used to be built per call, which was the same thing while a request meant one call. It is not any more: delivery opens further attempts after a torn body, long after the driver that opened the first has returned, and each of those would have arrived with a full budget of its own — `max_total` would have bounded a call rather than a request, which is not what it is named for.
    """
    if context.retry_ledger is None:
        context.retry_ledger = RetryLedger(chain.config.upstream_request_retry)
    return context.retry_ledger

def shape_request(
    chain: Chain,
    context: RequestContext,
    on_routed: Callable[[RequestContext], None] | None = None,
) -> tuple[ModelProvider, Route]:
    """Route the request and repair it, up to but not including translation.

    Shared by the two entry points because they are asking about the same request. A count taken from a body that had not been through these steps answers about a body nobody was going to send — and, since 2026-08-20, upstream refuses the counting request over the same defects it refuses the real one, in the same words.

    Translation is left to each caller rather than pulled in here, because they need it at different moments and for different reasons — the real request needs the carried body to send, the count needs it to measure — but both do translate, and both do it right after this returns.
    """
    provider = chain.providers.get(context.provider_name or chain.providers.default_name)
    route = decide_route(
        requested_model=context.requested_model,
        inbound_format=context.inbound_format,
        provider=provider,
        mappings=chain.config.model_mappings,
    )
    apply_route(context, route)
    if on_routed is not None:
        # Announced the moment the model is known rather than when the request finishes, because everything below this line can take tens of seconds and a display that waits for it reports "still deciding" for the whole upstream call. That is not slow feedback, it is wrong feedback.
        on_routed(context)

    # Before anything reads `client_headers` for the attempt, and after `apply_route` because until routing decides there is no answer to which path this is. `build_context` has already applied the floor, so this is a policy question rather than a safety one: `message-format-reshape.md` gives the direct path a blacklist and the translation path a whitelist, and today that whitelist is empty — a translated request forwards none of the client's headers, `anthropic-beta` included.
    context.client_headers = apply_path_header_policy(
        context.client_headers, translated=context.translation_required
    )

    if context.inbound_format is WireFormat.ANTHROPIC_MESSAGES:
        # After `apply_route` because the flags belong to the model the attempt is actually sent to, not to the name the client asked for; before the driver because the driver forwards `client_headers` whole and has no way to know which of them this model refuses. `message-format-reshape.md` scopes this to the Anthropic Messages endpoints, which is what the guard says.
        context.client_headers, stripped_flags = strip_denied_beta_flags(
            context.client_headers,
            model=context.resolved_model,
            denials=chain.beta_flag_denials,
        )
        for flag in stripped_flags:
            BETA_FLAGS_STRIPPED.labels(model=context.resolved_model, flag=flag).inc()

        # Before translation on purpose: these fixups read `messages`, which the target format may not have. The spec calls this point `on_client_request_parsed`.
        fix_anthropic_request(context.payload, chain.config.hook_fix_anthropic_request)
    return provider, route

async def handle(chain: Chain, context: RequestContext, on_routed: Callable[[RequestContext], None] | None = None) -> HandledRequest:
    provider, route = shape_request(chain, context, on_routed)

    if route.translation_required:
        translated, semantic = chain.translators.translate(
            context.payload,
            source=route.inbound_format,
            target=route.target_format,
            target_model=translation_target(provider, route.model_id),
        )
        context.payload = translated
        if not semantic.conversion.lossless:
            context.extras["conversion_losses"] = list(semantic.conversion.losses)

    # The payload names the inbound model; upstream must be asked for the resolved one.
    context.payload["model"] = route.model_id

    timeouts = chain.config.upstream_request_timeouts
    # Read straight off the field it names. It used to be resolved against `response_header_overrides`, which is a different setting entirely: an operator capping the header wait for one model would have capped that model's whole attempt instead, cutting a long turn short in the name of a guard that was never asked for.
    attempt_deadline = timeouts.upstream_request_deadline
    driver_type = DRIVERS[route.endpoint]
    driver = driver_type(
        provider,
        chain.subscribers,
        budget=LedgerBudget(
            ledger_for(context, chain),
            # Read at each refusal rather than sampled now: a drain that begins while this request is in flight has to stop the *next* attempt, and a value captured here would say "running" for the whole request.
            draining=lambda: chain.active_requests.draining,
        ),
        attempt_deadline=attempt_deadline,
        response_header_timeout=timeouts.response_header,
        rate_limiter=chain.rate_limiter_for(provider.name),
    )
    outcome = await driver.run(context)
    if isinstance(outcome.error, WebSearchNotExecutable):
        # Answered rather than failed. The client issues a search as its own sub-request and treats an HTTP error as a transport problem worth retrying — three times, in the one case on record — while a search that cannot run will not start working on the third attempt. A failed *tool* is not retried, so the reply says so in the protocol's own words.
        return HandledRequest(
            context=context,
            route=route,
            outcome=_answered_failed_search(context, route),
            synthesized=True,
        )
    return HandledRequest(context=context, route=route, outcome=outcome)

def _answered_failed_search(context: RequestContext, route: Route) -> DriverOutcome:
    """A reply this proxy writes, saying the search was attempted and did not run.

    Built as an upstream reply rather than as finished client bytes so it goes through the same assembler, buffer and delivery path as everything else. `synthesized` is what tells the delivery side to read it as Anthropic: the route still names whichever upstream would have answered, and that is what the console line should keep reporting.
    """
    query = query_from_request(context.payload)
    message_id = f"msg_{uuid4().hex[:24]}"
    call_id = f"srvtoolu_{uuid4().hex[:24]}"
    request = httpx2.Request("POST", "https://synthesized.invalid/messages", content=b"")
    if context.stream:
        body = failed_search_sse(
            query, message_id=message_id, model=route.model_id, call_id=call_id
        )
        headers = {"content-type": "text/event-stream"}
    else:
        body = dumps(
            failed_search_body(
                query, message_id=message_id, model=route.model_id, call_id=call_id
            )
        )
        headers = {"content-type": "application/json"}
    return DriverOutcome(
        context=context,
        response=httpx2.Response(200, content=body, headers=headers, request=request),
        attempts=context.attempt_count,
    )

class CountTokensRequestError(ValueError):
    """The body cannot be read as an Anthropic Messages request, so there is nothing to count."""

async def handle_count_tokens(chain: Chain, context: RequestContext) -> dict[str, Any]:
    """Serve `/v1/messages/count_tokens` through the provider chain the spec names.

    Shaped by `shape_request`, exactly like the request being measured: a count that ignored `model_mappings`, the capability gate, or the repairs the outbound body gets would answer about a different request than the one that would be asked.

    The two counters are not interchangeable. `ghc` returns upstream's own number and is worth learning from; `local` returns an estimate corrected by what has been learnt so far. So the answer says which one it came from rather than presenting an estimate as a measurement.
    """
    provider, route = shape_request(chain, context)

    # Translated too, and in the same order the real request takes it: shape, translate, name the resolved model, then let the subscribers see it. A count that stopped short of translation would be measuring an Anthropic body against a model that is never going to be sent one — `/responses` receives a different set of items, a different tool shape, and a different spelling of every role, and its tokenizer counts what arrives rather than what was asked.
    # This is also the only way the subscribers see here what they see in production: the driver publishes `attempt.prepare` after translation, so publishing it before would hand them a protocol they never meet on this route.
    if route.translation_required:
        translated, semantic = chain.translators.translate(
            context.payload,
            source=route.inbound_format,
            target=route.target_format,
            target_model=translation_target(provider, route.model_id),
        )
        context.payload = translated
        if not semantic.conversion.lossless:
            context.extras["conversion_losses"] = list(semantic.conversion.losses)
    context.payload["model"] = route.model_id

    context.begin_attempt()
    # Counting measures a body; it does not send one. A subscriber that refuses a request this endpoint cannot serve is right to do so on the leg that would have served it, and wrong here:
    # nothing is executed, no reply is produced, and there is therefore nothing that could come back invented. Refusing would only turn a question with an answer — how large is this — into an error, and push the client onto its local estimate for no gain.
    context.extras[COUNTING_ONLY] = True
    for subscription in chain.subscribers.for_event(EVENT_ATTEMPT_PREPARE):
        await subscription.handler(context)

    # One estimator per wire contract, and the calibration key follows it. The protocols' payload estimates stay separate so neither corrects the other with its own error; the same reason applies to the factor learnt from them. The idea came from `.dev/docs/archived-2604-rewrite/tokenization.md`, which the user ruled obsolete on 2026-08-20 — it is kept on the reasoning, not on that document's authority.
    protocol = route.target_format.value
    if route.target_format is WireFormat.ANTHROPIC_MESSAGES:
        protocol = "anthropic"
        estimate = estimate_anthropic_input(_countable(context.payload))
    elif route.target_format is WireFormat.OPENAI_RESPONSES:
        estimate = estimate_responses_input(context.payload)
    else:
        # Unreachable today and written to stay loud if that changes: the only outbound translators registered are Anthropic and Responses, so any other target already failed above with `TranslatorNotFound`. Add one — chat-completions is the obvious candidate, and three models in the catalogue advertise nothing else — and this branch opens. Reading a chat-completions body with the Responses estimator finds no `input` and no `instructions` and returns 1, which is not an estimate but a claim that the request is free.
        raise CountTokensRequestError(
            f"no token estimator for {route.target_format.value}; add one before routing counts there"
        )
    calibration = chain.tokenization.calibration

    async def ask_upstream(payload: Mapping[str, Any]) -> int:
        response = await provider.count_tokens(payload, model_id=route.model_id)
        # Taken before the body is read and before the response is closed, so the count line can report the leg it actually flew. Without these a count answered by upstream and one estimated in this process render identically apart from the counter's name — same missing byte fields, same single protocol label — and the line's own convention is that a missing field means the exchange had nothing to put there.
        # What the leg's presence means is narrower than "upstream answered the count": it means upstream *responded*. A refusal or a transport failure never reaches here — `send_anthropic_count_tokens` raises it as a pipeline error — but a 200 whose body carries no usable `input_tokens` does, and then the raise below hands the count to the estimator with both legs already recorded. `↑…B ↓…B … provider(ghc-failed,local)` is the right reading of that: upstream was asked, upstream replied, and the reply could not be used.
        context.extras["count_tokens_upstream_protocol"] = response.http_version
        context.extras["count_tokens_bytes_in"] = len(response.request.content)
        try:
            response.raise_for_status()
            body = cast(dict[str, Any], response.json())
            # After the body is in hand, so this is the whole of what upstream sent rather than however much had arrived. Recorded for the same reason as the outbound half: a leg reported in one direction only says, by this line's convention, that nothing came back.
            context.extras["count_tokens_bytes_out"] = len(response.content)
        finally:
            await response.aclose()
        counted = body.get("input_tokens")
        if not isinstance(counted, int) or counted <= 0:
            raise ValueError("upstream count_tokens gave no positive input_tokens")
        return counted

    def estimate_locally(payload: Mapping[str, Any]) -> int:
        del payload  # Already measured above; recomputing per attempt would only cost time.
        return calibration.calibrate(protocol, route.model_id, estimate)

    # Whether upstream has a counter is a property of where this is going, not of whether the request is serviceable. Token counting is a per-protocol wire contract, and the endpoint list in `docs/.human-controlled/api.md` is where that shows: `POST /v1/messages/count_tokens` serves the Anthropic protocol, and the OpenAI family has no count endpoint at all, reporting usage only on a finished response. A translated route is perfectly sendable and simply has no counter upstream, so it is answered from the estimator for its own protocol rather than refused.
    #
    # Withholding the counter is how that is said: `count_tokens()` already understands a missing one as "hand over to the next", so this needs no new failure mode. The reason travels with it into the attempts trail, because `ghc:unconfigured` against a config file that configures `ghc` would send the next reader hunting a settings bug that does not exist.
    #
    # A request no translator can carry never reaches here: `translate` above raises `TranslatorNotFound` exactly as it does for the request being counted, and the client gets the same 400 it would have got for sending it.
    upstream_counts = route.target_format is WireFormat.ANTHROPIC_MESSAGES

    settings = chain.config.inbound.anthropic_count_tokens
    payload = dict(context.payload)
    payload.pop("stream", None)
    absent_reason = f"no-counter-for-{route.target_format.value}"
    result = await count_tokens(
        payload,
        providers=settings.providers,
        max_retries=settings.max_retries,
        upstream=ask_upstream if upstream_counts else None,
        local=estimate_locally,
        upstream_absent_reason=absent_reason,
    )
    context.extras["count_tokens_provider"] = result.provider
    if result.attempts:
        context.extras["count_tokens_attempts"] = list(result.attempts)
    # Why the estimate answered, decided here because this is where the two facts that separate the cases live: the reason this function itself withheld the counter, and whether `ghc` was ever reached. Both readings put `local` on the line as the provider that answered and only one of them is an incident — a route with no upstream counter estimates every time and is working as configured, while an upstream that was asked and could not answer is something to look at. Left to the display layer they would be one string.
    # Read off the trail rather than off `upstream_counts`, because a counter can be withheld in three ways and only two of them are this function's doing: the operator can also leave `ghc` out of `providers`, or order `local` ahead of it, and then upstream was never asked and nothing failed. `ghc:` is the prefix `count_tokens` writes for every attempt against that provider, and the withheld case is the exact string handed to it above, so neither test has to guess at an entry's shape.
    if result.provider != "ghc":
        trail = result.attempts
        if f"ghc:{absent_reason}" in trail:
            context.extras["count_tokens_reason"] = "no-counter"
        elif any(entry.startswith("ghc:") for entry in trail):
            context.extras["count_tokens_reason"] = "ghc-failed"

    if result.provider == "ghc":
        # Upstream's number is ground truth for the estimator, which is the only way it improves.
        calibration.learn(protocol, route.model_id, estimate, result.tokens)
        return {"input_tokens": result.tokens}
    return {"input_tokens": result.tokens, "estimated": True}

def _countable(payload: Mapping[str, Any]) -> MessagesRequest:
    """Read the body as a Messages request for estimation only.

    `max_tokens` is required to *send* a Messages request but means nothing when counting its input, and Anthropic's own count_tokens endpoint does not ask for it. Supplying one here keeps a legitimate body from being rejected; it is never sent anywhere.
    """
    countable = dict(payload)
    countable.setdefault("max_tokens", 1)
    try:
        return MessagesRequest.model_validate(countable)
    except ValidationError as error:
        raise CountTokensRequestError(f"not a countable Messages body: {error}") from error

async def handle_bounded(
    chain: Chain,
    context: RequestContext,
    on_routed: Callable[[RequestContext], None] | None = None,
    *,
    deadline_at: float | None = None,
) -> HandledRequest:
    """Run a request under the client deadline, up to the point upstream's response headers arrive.

    It bounds the whole client-visible operation rather than any one attempt, and is never reset by a retry — but only a caller that admitted the request knows when the request began. `deadline_at` is how that caller says so; the fallback starts the clock here, which is later than admission by however long the body took to read and the request took to be routed. Measured 2026-08-22: with the clock started here, a body read, a JSON parse and a queue wait were all outside it.

    This covers a non-streaming reply whole, because its body is read before `handle` returns. A streaming body is not: `await send` returns at the response headers, so what arrives afterwards is bounded by the same instant enforced a second time, over the body, in `pipeline_app`.
    """
    deadline = chain.config.client_delivery.client_request_deadline
    if deadline <= 0:
        return await handle(chain, context, on_routed)
    bound = (
        asyncio.timeout_at(deadline_at)
        if deadline_at is not None
        else asyncio.timeout(deadline)
    )
    try:
        async with bound:
            return await handle(chain, context, on_routed)
    except TimeoutError as error:
        # 504 rather than 408, ruled 2026-08-22 and written into `client-side-block-delivery.md`.
        raise UpstreamTimeout(f"client request exceeded {deadline}s") from error
