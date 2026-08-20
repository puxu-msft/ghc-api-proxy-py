"""The request handler: inbound context to upstream response.

Order follows MAIN.md: route first, translate only when the formats differ, then drive.

Streaming is served by block-level delivery: the upstream response is read whole, its blocks are
put through the buffer, and only complete blocks are framed as Anthropic SSE. Nothing reaches the
client while a block is still forming.
"""

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

import httpx
from pydantic import ValidationError

from app.model_provider import ProviderError
from app.models.anthropic import MessagesRequest
from app.pipeline.anthropic_request_hook import fix_anthropic_request
from app.pipeline.count_tokens import CountTokensUnavailable, count_tokens
from app.pipeline.delivery import BlockBuffer, CompletedBlock, DeliverySession
from app.pipeline.delivery.assembler import (
    AnthropicAssembler,
    BlockAssembler,
    ReplyDialect,
    ResponsesAssembler,
    Terminal,
    terminal_from_anthropic,
)
from app.pipeline.delivery.stream import StreamSettings
from app.pipeline.direct_driver import (
    DRIVERS,
    EVENT_ATTEMPT_PREPARE,
    DriverOutcome,
    LedgerBudget,
)
from app.pipeline.exceptions import UpstreamRateLimit, UpstreamRejected, UpstreamTimeout
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.retry import RetryLedger
from app.pipeline.routing import Route, RoutingError, decide_route
from app.pipeline.timeouts import resolve_timeout
from app.pipeline.translation_driver.registry import TranslatorNotFound
from app.server.composition import Chain
from app.tokenization.estimators import estimate_anthropic_input


@dataclass(slots=True)
class HandledRequest:
    context: RequestContext
    route: Route
    outcome: DriverOutcome

    @property
    def response(self) -> httpx.Response | None:
        return self.outcome.response


def apply_route(context: RequestContext, route: Route) -> None:
    context.resolved_model = route.model_id
    context.provider_name = route.provider_name
    context.endpoint = route.endpoint
    context.target_format = route.target_format
    context.translation_required = route.translation_required
    context.route_reason = route.reason


async def handle(chain: Chain, context: RequestContext, on_routed: Callable[[RequestContext], None] | None = None) -> HandledRequest:
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

    if context.inbound_format is WireFormat.ANTHROPIC_MESSAGES:
        # Before translation on purpose: these fixups read `messages`, which the target format may
        # not have. The spec calls this point `on_client_request_parsed`.
        fix_anthropic_request(context.payload, chain.config.hook_fix_anthropic_request)

    if route.translation_required:
        translated, semantic = chain.translators.translate(
            context.payload,
            source=route.inbound_format,
            target=route.target_format,
        )
        context.payload = translated
        if not semantic.conversion.lossless:
            context.extras["conversion_losses"] = list(semantic.conversion.losses)

    # The payload names the inbound model; upstream must be asked for the resolved one.
    context.payload["model"] = route.model_id

    timeouts = chain.config.upstream_request_timeouts
    attempt_deadline = resolve_timeout(
        route.model_id,
        timeouts.upstream_request_deadline,
        timeouts.response_header_overrides,
    )
    driver_type = DRIVERS[route.endpoint]
    driver = driver_type(
        provider,
        chain.subscribers,
        budget=LedgerBudget(RetryLedger(chain.config.upstream_request_retry)),
        attempt_deadline=attempt_deadline,
        rate_limiter=chain.rate_limiter_for(provider.name),
    )
    outcome = await driver.run(context)
    return HandledRequest(context=context, route=route, outcome=outcome)


class CountTokensRequestError(ValueError):
    """The body cannot be read as an Anthropic Messages request, so there is nothing to count."""


async def handle_count_tokens(chain: Chain, context: RequestContext) -> dict[str, Any]:
    """Serve `/v1/messages/count_tokens` through the provider chain the spec names.

    Routed first, exactly like the request being measured: a count that ignored `model_mappings`
    or the capability gate would answer about a different model than the one that would be asked.

    The two providers are not interchangeable. `ghc` returns upstream's own number and is worth
    learning from; `local` returns an estimate corrected by what has been learnt so far. So the
    answer says which one it came from rather than presenting an estimate as a measurement.
    """
    provider = chain.providers.get(context.provider_name or chain.providers.default_name)
    route = decide_route(
        requested_model=context.requested_model,
        inbound_format=context.inbound_format,
        provider=provider,
        mappings=chain.config.model_mappings,
    )
    apply_route(context, route)
    context.payload["model"] = route.model_id

    # The same subscribers the driver runs, for the same reason: this is an upstream request too, and upstream rejects a counting request carrying a server-tool declaration in exactly the words it rejects the request being counted. Measured 2026-08-20.
    # Before the estimate rather than after, so what is measured is what would actually be sent.
    context.begin_attempt()
    for subscription in chain.subscribers.for_event(EVENT_ATTEMPT_PREPARE):
        await subscription.handler(context)

    estimate = estimate_anthropic_input(_countable(context.payload))
    calibration = chain.tokenization.calibration

    async def ask_upstream(payload: Mapping[str, Any]) -> int:
        response = await provider.count_tokens(payload, model_id=route.model_id)
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
        return calibration.calibrate("anthropic", route.model_id, estimate)

    settings = chain.config.inbound.anthropic_count_tokens
    payload = dict(context.payload)
    payload.pop("stream", None)
    result = await count_tokens(
        payload,
        providers=settings.providers,
        max_retries=settings.max_retries,
        upstream=ask_upstream,
        local=estimate_locally,
    )
    context.extras["count_tokens_provider"] = result.provider
    if result.attempts:
        context.extras["count_tokens_attempts"] = list(result.attempts)

    if result.provider == "ghc":
        # Upstream's number is ground truth for the estimator, which is the only way it improves.
        calibration.learn("anthropic", route.model_id, estimate, result.tokens)
        return {"input_tokens": result.tokens}
    return {"input_tokens": result.tokens, "estimated": True}


def _countable(payload: Mapping[str, Any]) -> MessagesRequest:
    """Read the body as a Messages request for estimation only.

    `max_tokens` is required to *send* a Messages request but means nothing when counting its
    input, and Anthropic's own count_tokens endpoint does not ask for it. Supplying one here keeps
    a legitimate body from being rejected; it is never sent anywhere.
    """
    countable = dict(payload)
    countable.setdefault("max_tokens", 1)
    try:
        return MessagesRequest.model_validate(countable)
    except ValidationError as error:
        raise CountTokensRequestError(f"not a countable Messages body: {error}") from error


async def handle_bounded(chain: Chain, context: RequestContext, on_routed: Callable[[RequestContext], None] | None = None) -> HandledRequest:
    """Run a request under the client deadline.

    Measured from admission and never reset by a retry, so it bounds the whole client-visible
    operation rather than any one attempt.
    """
    deadline = chain.config.client_delivery.client_request_deadline
    if deadline <= 0:
        return await handle(chain, context, on_routed)
    try:
        async with asyncio.timeout(deadline):
            return await handle(chain, context, on_routed)
    except TimeoutError as error:
        raise UpstreamTimeout(f"client request exceeded {deadline}s") from error


def error_status(error: BaseException) -> int:
    """Map a failure to the status the client should see.

    A routing or capability refusal means the request is unserviceable, not that upstream failed.
    It must not be reported as a bad gateway.

    Nor must an upstream answer be flattened into one. A client that gets 429 can back off and a
    client that gets 400 can fix its body; both learn nothing from a 502, which says the proxy
    itself broke. Everything used to land on that 502 because the SDK's exceptions were outside
    the closed set — see `app.ghc_client.errors`.
    """
    if isinstance(
        error,
        ProviderError | RoutingError | TranslatorNotFound | CountTokensRequestError,
    ):
        return 400
    if isinstance(error, CountTokensUnavailable):
        # Every configured counter failed. Reachable when `providers` names only `ghc`;
        # with `local` in the list the estimate has no way to fail on the normal path.
        return 503
    if isinstance(error, UpstreamRateLimit):
        return 429
    if isinstance(error, UpstreamTimeout):
        return 504
    if isinstance(error, UpstreamRejected):
        # Upstream's own verdict on the request. Passed through so the client is told what is
        # wrong with what it sent, rather than that some gateway failed.
        return error.status_code
    return 502


def error_headers(error: BaseException) -> dict[str, str]:
    """The few upstream headers a client needs in order to act on a failure.

    `Retry-After` only: it is the one that changes what a well-behaved client does next. An
    allowlist rather than forwarding upstream's set, which carries its own framing headers.
    """
    if isinstance(error, UpstreamRateLimit) and error.retry_after is not None:
        return {"retry-after": str(int(error.retry_after))}
    return {}


def error_body(error: BaseException) -> dict[str, Any]:
    body: dict[str, Any] = {"type": type(error).__name__, "message": str(error)}
    upstream = getattr(error, "body", "")
    if isinstance(upstream, str) and upstream:
        # What upstream actually said. Named as upstream's rather than merged, so nothing reads
        # our wrapper's wording as though the model had produced it.
        body["upstream"] = upstream
    return {"error": body}


def response_payload(chain: Chain, handled: HandledRequest, body: dict[str, Any]) -> dict[str, Any]:
    """Bring an upstream body back to the format the client asked in.

    Without this a translated route answers in the upstream's shape, which the client did not ask
    for and cannot parse.
    """
    route = handled.route
    if not route.translation_required:
        return body
    translated, semantic = chain.translators.translate_response(
        body,
        source=route.target_format,
        target=route.inbound_format,
    )
    if not semantic.conversion.lossless:
        handled.context.extras["response_conversion_losses"] = list(semantic.conversion.losses)
    return translated


def blocks_from_anthropic(body: dict[str, Any]) -> list[CompletedBlock]:
    """Read the content blocks out of an Anthropic-shaped response body."""
    content = body.get("content")
    if not isinstance(content, list):
        return []
    blocks: list[CompletedBlock] = []
    for index, raw in enumerate(cast(list[object], content)):
        if not isinstance(raw, dict):
            continue
        payload = cast(dict[str, Any], raw)
        blocks.append(
            CompletedBlock(index=index, kind=str(payload.get("type", "")), payload=payload)
        )
    return blocks


def deliver_blocks(chain: Chain, blocks: list[CompletedBlock]) -> list[CompletedBlock]:
    """Put blocks through the buffer so the configured policy and cap apply.

    Every block here is already complete, so what the buffer decides is ordering and holding, not
    whether a block is whole.
    """
    delivery = chain.config.client_delivery
    session = DeliverySession(
        buffer=BlockBuffer(
            policy=delivery.buffering_policy,
            cap_bytes=delivery.buffer_cap_bytes,
        )
    )
    committed: list[CompletedBlock] = []
    for block in blocks:
        committed.extend(session.offer(block))
    committed.extend(session.finish())
    return committed


def dialect_for(handled: HandledRequest) -> ReplyDialect:
    """Which upstream's vocabulary this route's reply came back in.

    Taken from the route rather than from the reply, because a buffered reply is read back after translation and by then looks Anthropic-shaped whatever answered it. The route is the only thing that still knows which upstream was actually spoken to, which is what the console line reports.

    Two dialects, not one per wire format: anything that is not a Responses upstream is assembled as Anthropic — `assembler_for` below dispatches on this very answer — so the pair describes what the code actually does rather than the whole `WireFormat` taxonomy. A third upstream would need its own assembler before it could need its own words.
    """
    if handled.route.target_format is WireFormat.OPENAI_RESPONSES:
        return ReplyDialect.RESPONSES
    return ReplyDialect.ANTHROPIC


def reply_summary(handled: HandledRequest, payload: dict[str, Any]) -> Terminal | None:
    """Summarise a buffered reply for the console line, or `None` when this route's shape cannot be read.

    `payload` is in the **client's** format by the time it gets here, which is what decides whether it can be read at all: only an Anthropic-shaped body has the `content` blocks the reader wants. An inbound `/responses` or `/chat/completions` request keeps its own shape end to end, and reading one of those as Anthropic finds nothing — silently, since an absent `content` is indistinguishable from a reply that had none.

    Returning `None` rather than an empty summary is the honest answer: those lines carry no reasoning or tool fields today, which is a gap worth closing but not one to paper over with a record that says a reply had nothing in it. See `docs/agents/tui-request-log/deferred.md`.

    The dialect is separate and comes from the route, because which *words* to use is about the upstream leg while which *reader* to use is about the client leg, and on a translated route those are two different formats.
    """
    if handled.route.inbound_format is not WireFormat.ANTHROPIC_MESSAGES:
        return None
    return terminal_from_anthropic(payload, blocks_from_anthropic(payload), dialect=dialect_for(handled))


def assembler_for(handled: HandledRequest) -> BlockAssembler:
    """Pick the assembler matching the upstream this route actually used.

    Dispatched on `dialect_for` rather than testing the wire format again, so the streaming and buffered paths cannot come to disagree about which upstream answered — one branch decides it for both.
    """
    if dialect_for(handled) is ReplyDialect.RESPONSES:
        return ResponsesAssembler()
    return AnthropicAssembler()


def stream_settings(chain: Chain) -> StreamSettings:
    delivery = chain.config.client_delivery
    return StreamSettings(
        signature_compat=chain.config.hook_fix_anthropic_sse.thinking.content_block_start_compat,
        sse_ping_interval=delivery.sse_ping_interval,
        synthesized_response_headers_after_sec=(
            delivery.synthesized_response_headers_after_sec
        ),
    )


def delivery_buffer(chain: Chain) -> BlockBuffer:
    delivery = chain.config.client_delivery
    return BlockBuffer(
        policy=delivery.buffering_policy,
        cap_bytes=delivery.buffer_cap_bytes,
    )
