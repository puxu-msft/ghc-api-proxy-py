"""The single owner of a request's life: route it, send it, and hand back what came.

Split out of `app.server.handler` on 2026-08-22. `docs/.human-controlled/request-pipeline.md` gives `app.pipeline` the driving and `app.server` the inbound HTTP surface, and the driving had grown inside the surface. `D-ARCH = B` says the same thing from the other side: one owner for approval, attempt, retry, transport exchange and finalize, and nothing else starting a second request lifecycle.

What is *not* here is deliberate. Rendering a failure as HTTP belongs to the edge (`app.server.http_errors`), reading a finished reply back in the client's vocabulary is `app.pipeline.reply`, and choosing a framer or an assembler is `app.pipeline.delivery_policy`.
"""

import asyncio
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

import httpx2
from pydantic import ValidationError

from app.config.schema import LOCAL_COUNTER
from app.core.chain import Chain
from app.model_provider import ModelDescriptor, ModelProvider
from app.models.anthropic import MessagesRequest
from app.observability.metrics import BETA_FLAGS_STRIPPED
from app.pipeline.anthropic_request_hook import fix_anthropic_request
from app.pipeline.auto_mode_classifier import AutoModeVerdict, classify, log_hit, verdict_text
from app.pipeline.count_tokens import CountTokensRequestError, count_tokens
from app.pipeline.delivery.formats.anthropic_messages_synthetic_reply import (
    auto_mode_body,
    auto_mode_sse,
    failed_search_body,
    failed_search_sse,
    query_from_request,
)
from app.pipeline.direct_driver import (
    DRIVERS,
    EVENT_ATTEMPT_PREPARE,
    EVENT_REQUEST_SUCCEEDED,
    DriverOutcome,
    LedgerBudget,
)
from app.pipeline.exceptions import (
    UpstreamTimeout,
)
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.request_headers import (
    apply_path_header_policy,
    strip_denied_beta_flags,
    strip_gateway_unsupported_betas,
)
from app.pipeline.retry import RetryLedger
from app.pipeline.routing import Route, apply_route, decide_route, translation_target
from app.pipeline.subscribers.counting import COUNTING_ONLY
from app.pipeline.translation_driver.semantic import (
    WebSearchNotExecutable,
)
from app.tokenization.admission import TokenAdmissionObservation
from app.tokenization.estimators import estimate_anthropic_input, estimate_responses_input
from app.tokenization.scaling import scale_local_estimate
from app.wire_json import dumps

# Where request-translation facts are kept for the response half. Neither kind of Responses search call carries enough information to recover these decisions from the response itself.
CLIENT_SEARCH_TOOL = "client_search_tool"
HOSTED_WEB_SEARCH_EXPECTED = "hosted_web_search_expected"
RESPONSE_CONVERSION_LOSSES = "response_conversion_losses"

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
    # The provider is routing's answer, not routing's input. It used to be read off the context here — `context.provider_name or default_name` — which looked like a seam for per-model routing but never was one: the only writer of that field is `apply_route`, two lines below, so it was empty on every arriving request and the `or` resolved to the default every time.
    route = decide_route(
        requested_model=context.requested_model,
        inbound_format=context.inbound_format,
        providers=chain.providers,
        mappings=chain.config.model_mappings,
    )
    provider = chain.providers.get(route.provider_name)
    apply_route(context, route)
    if on_routed is not None:
        # Announced the moment the model is known rather than when the request finishes, because everything below this line can take tens of seconds and a display that waits for it reports "still deciding" for the whole upstream call. That is not slow feedback, it is wrong feedback.
        on_routed(context)

    # Before anything reads `client_headers` for the attempt, and after `apply_route` because until routing decides there is no answer to which path this is. `build_context` has already applied the floor, so this is a policy question rather than a safety one: `message-format-reshape.md` gives the direct path a blacklist and the translation path a whitelist, and today that whitelist is empty — a translated request forwards none of the client's headers, `anthropic-beta` included.
    context.client_headers = apply_path_header_policy(
        context.client_headers, translated=context.translation_required
    )

    if context.inbound_format is WireFormat.ANTHROPIC_MESSAGES:
        # Before the per-model strip below, though nothing forces the order: the two tables are disjoint by construction and a flag in both would be removed by whichever ran first. First because it is the coarser question — the gateway refuses these names before any model is consulted, so a reader following the header's fate meets the deployment-wide filter before the per-model one.
        context.client_headers, gateway_stripped = strip_gateway_unsupported_betas(
            context.client_headers
        )
        for flag in gateway_stripped:
            BETA_FLAGS_STRIPPED.labels(model=context.resolved_model, flag=flag).inc()

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
    descriptor = route.descriptor
    if descriptor is None:
        raise RuntimeError("routed request has no model descriptor")

    # Before translation, because the predicates read `system` and `messages` and the target format has neither. Before the driver, because the whole point is that no upstream call happens: this is the one path where the reply is decided without an attempt.
    #
    # **Gated on the inbound format, not only on the body.** The reply this synthesises is an Anthropic Message, and the request it recognises is defined as a non-streaming `/v1/messages`. Without this guard a Chat Completions request whose content parts happened to match the markers was answered with an Anthropic body on the `/chat/completions` path — a protocol the caller has no reason to be able to read, for a request that never reached upstream. The predicates are the wrong tool for deciding which endpoint a body arrived on; the route already knows.
    if context.inbound_format is WireFormat.ANTHROPIC_MESSAGES:
        verdict = classify(
            context.payload, chain.config.hook_fix_anthropic_request.intercept_auto_mode_classifier
        )
        if verdict is not None:
            outcome = _answered_auto_mode(context, route, verdict, chain)
            # The client request succeeded, so the request-level event fires even though no attempt did. The attempt-level ones deliberately do not: there was no upstream leg for them to describe, and `attempt.prepare` subscribers exist to shape a body that is about to be sent.
            #
            # Published here rather than inside the driver because the driver is never built on this path. A subscriber raising propagates, which is the same contract it has inside the driver — there it steers the retry loop, and here there is no loop to steer, so it reaches the caller.
            outcome.events.append(EVENT_REQUEST_SUCCEEDED)
            for subscription in chain.subscribers.for_event(EVENT_REQUEST_SUCCEEDED):
                await subscription.handler(context)
            return HandledRequest(
                context=context,
                route=route,
                outcome=outcome,
                synthesized=True,
            )

    if route.translation_required:
        translated, semantic = chain.translators.translate(
            context.payload,
            source=route.inbound_format,
            target=route.target_format,
            target_model=translation_target(descriptor),
        )
        context.payload = translated
        if semantic.client_search_tool:
            # Kept for the response half, which cannot recover it: a `tool_search_call` names no tool, so without this the model's search request has no name to come back under.
            context.extras[CLIENT_SEARCH_TOOL] = semantic.client_search_tool
        if semantic.hosted_web_search_expected:
            # The same `web_search_call` spelling can be requested or unsolicited. Only the request translator knows which one this turn permits D6 to revive as a native pair.
            context.extras[HOSTED_WEB_SEARCH_EXPECTED] = True
        if not semantic.conversion.lossless:
            context.extras["conversion_losses"] = list(semantic.conversion.losses)

    # The payload names the inbound model; upstream must be asked for the resolved one.
    context.payload["model"] = route.model_id

    return await _drive(chain, context, provider, route, descriptor)


async def replay_prepared(
    chain: Chain,
    context: RequestContext,
    route: Route,
    prepared_payload: Mapping[str, Any],
    reused_admission: TokenAdmissionObservation,
    on_routed: Callable[[RequestContext], None] | None = None,
) -> HandledRequest:
    """Replay the exact final payload that produced the stream now being delivered."""
    descriptor = route.descriptor
    if descriptor is None:
        raise RuntimeError("replay route has no model descriptor")
    provider = chain.providers.get(route.provider_name)
    apply_route(context, route)
    if on_routed is not None:
        on_routed(context)
    context.payload = deepcopy(dict(prepared_payload))
    return await _drive(
        chain,
        context,
        provider,
        route,
        descriptor,
        prepared_payload=prepared_payload,
        reused_admission=reused_admission,
    )


async def _drive(
    chain: Chain,
    context: RequestContext,
    provider: ModelProvider,
    route: Route,
    descriptor: ModelDescriptor,
    *,
    prepared_payload: Mapping[str, Any] | None = None,
    reused_admission: TokenAdmissionObservation | None = None,
) -> HandledRequest:
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
        descriptor=descriptor,
        admission=chain.prompt_token_admission,
        prepared_payload=prepared_payload,
        reused_admission=reused_admission,
    )
    outcome = await driver.run(context)
    if isinstance(outcome.error, WebSearchNotExecutable) and context.inbound_format is WireFormat.ANTHROPIC_MESSAGES:
        # Answered rather than failed. The client issues a search as its own sub-request, and on an HTTP error its main-conversation model calls the tool again — three times before it gave up, in the one case on record — while a search that cannot run will not start working on the third attempt. No client *mechanism* repeats a failed tool result, so the reply says so in the protocol's own words. (Whether the model repeats one anyway is unmeasured; see `anthropic_messages_synthetic_reply`.)
        #
        # **The retries are the model's, not the transport's**, and this said the opposite until 2026-08-30. Claude Code's transport (`Ftw()`) does not retry a 400 at all; 408, 409, 401, 5xx and usually 429 it does, ten times by default and more if configured. So the three on record were three fresh sub-requests the model asked for. The trade stands — three round trips wasted either way — but the mechanism named here has to be the real one, or the next reader tests it against a 5xx and finds it false.
        #
        # **Gated on the inbound format, for the reason the auto mode branch above already states**: what this synthesises is an Anthropic Message, and handing one to a client that asked in another protocol answers it in a vocabulary it has no reason to read. The two branches now say the same thing; this one used to be reachable on any leg, and issue #1 is what that cost.
        #
        # Reachable from a `/responses` request even after the search gate stopped judging one, so this is not a second lock on the same door. A model that only supports `/v1/messages` routes an inbound Responses request onto the Anthropic leg, where `to_anthropic_messages` assigns `tools` across **verbatim** — the bare declaration stays bare — and `builtin:server-tool-capability` refuses it because its prefix table catches the bare spelling too. Delivery then frames by the *client's* leg: streaming tore on `ValueError: no Responses item shape for block kind 'server_tool_use'`, and non-streaming was worse — a 200, logged `ok`, carrying an Anthropic message body to a Responses client with nothing anywhere saying so. Both measured 2026-08-30.
        #
        # Falling through leaves `outcome` carrying the refusal, which becomes an error envelope in the client's own format. That is the honest answer here: the synthesis exists to spare one specific client the repeat calls an HTTP error drew from it, and a client that cannot read the synthesis gains nothing from it.
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

def _answered_auto_mode(
    context: RequestContext, route: Route, verdict: AutoModeVerdict, chain: Chain
) -> DriverOutcome:
    """The authorisation decision this proxy made, dressed as the reply upstream would have sent.

    Built as an upstream reply rather than as finished client bytes, for the reason its sibling above gives: it then travels the same assembler, buffer and delivery path as everything else, instead of being the one response in the system whose framing nothing has exercised. `synthesized` tells the delivery side to read it as Anthropic while the route keeps naming the upstream that would have answered, so the console line still reports where this request was headed.

    The size is measured off `original_payload` — the body as the client sent it, before the fixups — because that is the request this feature exists to not send. It is **a re-serialisation, not the received byte count**: whitespace, key order and Unicode escaping may all differ from what arrived, and the received length is not kept anywhere (`inference.py` reads the body and does not record how long it was). Close enough to say what was saved, and not the same number as `content-length`.
    """
    text = verdict_text(verdict, chain.config.hook_fix_anthropic_request.intercept_auto_mode_classifier.block_reason_str)
    source = context.original_payload or context.payload
    log_hit(verdict, request_bytes=len(dumps(source)))

    message_id = f"msg_{uuid4().hex[:24]}"
    request = httpx2.Request("POST", "https://synthesized.invalid/messages", content=b"")
    if context.stream:
        body = auto_mode_sse(text, message_id=message_id, model=route.model_id)
        headers = {"content-type": "text/event-stream"}
    else:
        body = dumps(auto_mode_body(text, message_id=message_id, model=route.model_id))
        headers = {"content-type": "application/json"}
    return DriverOutcome(
        context=context,
        response=httpx2.Response(200, content=body, headers=headers, request=request),
        attempts=context.attempt_count,
    )

async def handle_count_tokens(
    chain: Chain,
    context: RequestContext,
    on_routed: Callable[[RequestContext], None] | None = None,
    on_upstream_response: Callable[[RequestContext], None] | None = None,
) -> dict[str, Any]:
    """Serve `/v1/messages/count_tokens` through the provider chain the spec names.

    Shaped by `shape_request`, exactly like the request being measured: a count that ignored `model_mappings`, the capability gate, or the repairs the outbound body gets would answer about a different request than the one that would be asked.

    The two counters are not interchangeable. A model provider returns upstream's own number and is worth learning from; `local` returns an estimate corrected by what has been learnt so far. So the answer says which one it came from rather than presenting an estimate as a measurement.
    """
    provider, route = shape_request(chain, context)
    descriptor = route.descriptor
    if descriptor is None:
        raise RuntimeError("count route has no model descriptor")
    if on_routed is not None:
        on_routed(context)

    # Translated too, and in the same order the real request takes it: shape, translate, name the resolved model, then let the subscribers see it. A count that stopped short of translation would be measuring an Anthropic body against a model that is never going to be sent one — `/responses` receives a different set of items, a different tool shape, and a different spelling of every role, and its tokenizer counts what arrives rather than what was asked.
    # This is also the only way the subscribers see here what they see in production: the driver publishes `attempt.prepare` after translation, so publishing it before would hand them a protocol they never meet on this route.
    if route.translation_required:
        translated, semantic = chain.translators.translate(
            context.payload,
            source=route.inbound_format,
            target=route.target_format,
            target_model=translation_target(descriptor),
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
        response = await provider.count_tokens(payload, descriptor=descriptor)
        # Taken before the body is read and before the response is closed, so the count line can report the leg it actually flew. Without these a count answered by upstream and one estimated in this process render identically apart from the counter's name — same missing byte fields, same single protocol label — and the line's own convention is that a missing field means the exchange had nothing to put there.
        # What the leg's presence means is narrower than "upstream answered the count": it means upstream *responded*. A refusal or a transport failure never reaches here — `send_anthropic_count_tokens` raises it as a pipeline error — but a 200 whose body carries no usable `input_tokens` does, and then the raise below hands the count to the estimator with both legs already recorded. `↑…B ↓…B … provider(ghc-failed,local)` is the right reading of that: upstream was asked, upstream replied, and the reply could not be used.
        context.extras["count_tokens_upstream_protocol"] = response.http_version
        context.extras["count_tokens_upstream_request_bytes"] = len(response.request.content)
        # The SDK has already buffered the complete body at this point. Record its measured length before status/JSON interpretation so an empty or malformed answer remains an observed 0/N rather than becoming "unknown" on the fallback path.
        context.extras["count_tokens_upstream_response_bytes"] = len(response.content)
        if on_upstream_response is not None:
            on_upstream_response(context)
        try:
            response.raise_for_status()
            body = cast(dict[str, Any], response.json())
        finally:
            await response.aclose()
        counted = body.get("input_tokens")
        if not isinstance(counted, int) or counted <= 0:
            raise ValueError("upstream count_tokens gave no positive input_tokens")
        return counted

    def estimate_locally(payload: Mapping[str, Any]) -> int:
        del payload  # Already measured above; recomputing per attempt would only cost time.
        return scale_local_estimate(
            calibration.calibrate(protocol, route.model_id, estimate),
            settings.local_estimate_multiplier,
        )

    # Whether upstream has a counter is a property of where this is going, not of whether the request is serviceable. Token counting is a per-protocol wire contract, and the endpoint list in `docs/.human-controlled/api.md` is where that shows: `POST /v1/messages/count_tokens` serves the Anthropic protocol, and the OpenAI family has no count endpoint at all, reporting usage only on a finished response. A translated route is perfectly sendable and simply has no counter upstream, so it is answered from the estimator for its own protocol rather than refused.
    #
    # Withholding the counter is how that is said: `count_tokens()` already understands a missing one as "hand over to the next", so this needs no new failure mode. The reason travels with it into the attempts trail, because `ghc:unconfigured` against a config file that does list `ghc` would send the next reader hunting a settings bug that does not exist.
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
    # Why the estimate answered, decided here because this is where the two facts that separate the cases live: the reason this function itself withheld the counter, and whether any provider leg was ever reached. Both readings put `local` on the line as the leg that answered and only one of them is an incident — a route with no upstream counter estimates every time and is working as configured, while a provider that was asked and could not answer is something to look at. Left to the display layer they would be one string.
    # Read off the trail rather than off `upstream_counts`, because a counter can be withheld in three ways and only two of them are this function's doing: the operator can also leave every provider out of `providers`, or order `local` ahead of them, and then no provider was ever asked and nothing failed. Every entry `count_tokens` writes is prefixed with the leg's own name, so "not local" identifies the provider legs without this having to know what any of them is called.
    if result.provider == LOCAL_COUNTER:
        provider_attempts = [
            entry for entry in result.attempts if not entry.startswith(f"{LOCAL_COUNTER}:")
        ]
        if any(entry.endswith(f":{absent_reason}") for entry in provider_attempts):
            context.extras["count_tokens_reason"] = "no-counter"
        elif provider_attempts:
            # Named after the provider that failed rather than a generic word: with two configured, which one could not answer is the whole of what the line is for.
            context.extras["count_tokens_reason"] = (
                f"{provider_attempts[0].partition(':')[0]}-failed"
            )

    if result.provider != LOCAL_COUNTER:
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
