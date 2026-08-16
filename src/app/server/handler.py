"""The request handler: inbound context to upstream response.

Order follows MAIN.md: route first, translate only when the formats differ, then drive.

Streaming is served by block-level delivery: the upstream response is read whole, its blocks are
put through the buffer, and only complete blocks are framed as Anthropic SSE. Nothing reaches the
client while a block is still forming.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, cast

import httpx

from app.model_provider import ProviderError
from app.pipeline.delivery import BlockBuffer, CompletedBlock, DeliverySession
from app.pipeline.direct_driver import DRIVERS, DriverOutcome, LedgerBudget
from app.pipeline.exceptions import UpstreamTimeout
from app.pipeline.request import RequestContext
from app.pipeline.retry import RetryLedger
from app.pipeline.routing import Route, RoutingError, decide_route
from app.pipeline.timeouts import resolve_timeout
from app.pipeline.translation_driver import TranslatorNotFound
from app.server.composition import Chain


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


async def handle(chain: Chain, context: RequestContext) -> HandledRequest:
    provider = chain.providers.get(context.provider_name or chain.providers.default_name)
    route = decide_route(
        requested_model=context.requested_model,
        inbound_format=context.inbound_format,
        provider=provider,
        mappings=chain.config.model_mappings,
    )
    apply_route(context, route)

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


async def handle_bounded(chain: Chain, context: RequestContext) -> HandledRequest:
    """Run a request under the client deadline.

    Measured from admission and never reset by a retry, so it bounds the whole client-visible
    operation rather than any one attempt.
    """
    deadline = chain.config.client_delivery.client_request_deadline
    if deadline <= 0:
        return await handle(chain, context)
    try:
        async with asyncio.timeout(deadline):
            return await handle(chain, context)
    except TimeoutError as error:
        raise UpstreamTimeout(f"client request exceeded {deadline}s") from error


def error_status(error: BaseException) -> int:
    """Map a pre-network failure to a status code.

    A routing or capability refusal means the request is unserviceable, not that upstream failed.
    It must not be reported as a bad gateway.
    """
    if isinstance(error, ProviderError | RoutingError | TranslatorNotFound):
        return 400
    return 502


def error_body(error: BaseException) -> dict[str, Any]:
    return {"error": {"type": type(error).__name__, "message": str(error)}}


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
