"""The request result handed from the pipeline driver to the HTTP edge."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx2

from app.pipeline.delivery.assembling import BlockAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.framing import OutboundFramer
from app.pipeline.direct_driver import DriverOutcome
from app.pipeline.request import RequestContext
from app.pipeline.routing import Route

RESPONSE_CONVERSION_LOSSES = "response_conversion_losses"
RESPONSE_CONVERSION_WARNINGS = "response_conversion_warnings"
RESPONSE_CONVERSION_OPAQUE_PAYLOADS = "response_conversion_opaque_payloads"


@dataclass(frozen=True, slots=True)
class DeliveryPlan:
    assembler: BlockAssembler[Any]
    buffer: BlockBuffer[Any]
    framer: OutboundFramer[Any] | None


@dataclass(slots=True)
class HandledRequest:
    context: RequestContext
    route: Route
    outcome: DriverOutcome
    # A synthetic response is already in the inbound client's dialect.
    synthesized: bool = False
    # The driver remains the owner of opening a replacement attempt. Delivery
    # decides whether a failure is eligible, then calls this action.
    reopen: Callable[[Exception], Awaitable[HandledRequest | None]] | None = None
    delivery_plan: Callable[[Callable[[], None] | None], DeliveryPlan] | None = None

    @property
    def response(self) -> httpx2.Response | None:
        return self.outcome.response


__all__ = [
    "RESPONSE_CONVERSION_LOSSES",
    "RESPONSE_CONVERSION_OPAQUE_PAYLOADS",
    "RESPONSE_CONVERSION_WARNINGS",
    "DeliveryPlan",
    "HandledRequest",
]
