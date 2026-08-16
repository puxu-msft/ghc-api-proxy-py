"""The request handler: inbound context to upstream response.

Order follows MAIN.md: route first, translate only when the formats differ, then drive.

Streaming is refused here rather than passed through.
The spec requires block-level delivery.
Raw pass-through would break that invariant while appearing to work.
"""

from dataclasses import dataclass
from typing import Any

import httpx

from app.model_provider import ProviderError
from app.pipeline.direct_driver import DRIVERS, DriverOutcome, LedgerBudget
from app.pipeline.request import RequestContext
from app.pipeline.retry import RetryLedger
from app.pipeline.routing import Route, RoutingError, decide_route
from app.pipeline.translation_driver import TranslatorNotFound
from app.server.composition import Chain


class StreamingNotWired(RuntimeError):
    """Block-level delivery is not built yet, so streaming cannot be served correctly."""


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
    if context.stream:
        raise StreamingNotWired("streaming is not served by this path yet")

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

    driver_type = DRIVERS[route.endpoint]
    driver = driver_type(
        provider,
        chain.subscribers,
        budget=LedgerBudget(RetryLedger(chain.config.upstream_request_retry)),
    )
    outcome = await driver.run(context)
    return HandledRequest(context=context, route=route, outcome=outcome)


def error_status(error: BaseException) -> int:
    """Map a pre-network failure to a status code.

    A routing or capability refusal means the request is unserviceable, not that upstream failed.
    It must not be reported as a bad gateway.
    """
    if isinstance(error, StreamingNotWired):
        return 501
    if isinstance(error, ProviderError | RoutingError | TranslatorNotFound):
        return 400
    return 502


def error_body(error: BaseException) -> dict[str, Any]:
    return {"error": {"type": type(error).__name__, "message": str(error)}}
