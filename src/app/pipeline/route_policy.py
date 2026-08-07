from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum


class ProtocolLeg(StrEnum):
    MESSAGES = "messages"
    RESPONSES = "responses"


class RouteDecisionReason(StrEnum):
    EXPLICIT_OVERRIDE = "explicit_override"
    DUAL_CAPABILITY_DEFAULT = "dual_capability_default"
    SINGLE_CAPABILITY = "single_capability"


class RouteDecisionSource(StrEnum):
    ROUTE_OVERRIDE = "route_override"
    MODEL_CATALOG = "model_catalog"


class RouteDecisionErrorCode(StrEnum):
    MODEL_NOT_FOUND = "model_not_found"
    CAPABILITY_MISSING = "capability_missing"
    CAPABILITY_CONFLICT = "capability_conflict"
    OVERRIDE_UNSUPPORTED = "override_unsupported"
    TRANSPORT_UNAVAILABLE = "transport_unavailable"


@dataclass(frozen=True, slots=True)
class ResolvedModelFacts:
    resolved_model: str
    supported_endpoints: Collection[str] | None
    capability_source: str = "model_catalog"
    capability_conflict: str | None = None


@dataclass(frozen=True, slots=True)
class TransportAvailability:
    messages_http: bool = False
    responses_http: bool = False
    responses_websocket: bool = False

    def supports(self, leg: ProtocolLeg) -> bool:
        if leg is ProtocolLeg.MESSAGES:
            return self.messages_http
        return self.responses_http or self.responses_websocket


@dataclass(frozen=True, slots=True)
class RouteDecision:
    protocol_leg: ProtocolLeg
    reason: RouteDecisionReason
    source: RouteDecisionSource
    capability_source: str


class RouteDecisionError(ValueError):
    def __init__(
        self,
        code: RouteDecisionErrorCode,
        *,
        resolved_model: str | None,
        detail: str,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.resolved_model = resolved_model
        self.detail = detail


_MESSAGES_ENDPOINTS = frozenset({"/v1/messages"})
_RESPONSES_ENDPOINTS = frozenset({"/responses", "ws:/responses"})


def decide_protocol_leg(
    model: ResolvedModelFacts | None,
    *,
    override: ProtocolLeg | None = None,
    transports: TransportAvailability,
) -> RouteDecision:
    if model is None:
        raise RouteDecisionError(
            RouteDecisionErrorCode.MODEL_NOT_FOUND,
            resolved_model=None,
            detail="resolved model is absent from the model catalog",
        )

    endpoints = _validated_endpoints(model)
    supports_messages = bool(endpoints & _MESSAGES_ENDPOINTS)
    supports_responses = bool(endpoints & _RESPONSES_ENDPOINTS)

    if override is not None:
        if not _supports_leg(override, supports_messages, supports_responses):
            raise RouteDecisionError(
                RouteDecisionErrorCode.OVERRIDE_UNSUPPORTED,
                resolved_model=model.resolved_model,
                detail=f"model does not advertise {override.value} capability",
            )
        return _require_transport(
            model,
            transports,
            RouteDecision(
                protocol_leg=override,
                reason=RouteDecisionReason.EXPLICIT_OVERRIDE,
                source=RouteDecisionSource.ROUTE_OVERRIDE,
                capability_source=model.capability_source,
            ),
        )

    if supports_messages and supports_responses:
        decision = RouteDecision(
            protocol_leg=ProtocolLeg.MESSAGES,
            reason=RouteDecisionReason.DUAL_CAPABILITY_DEFAULT,
            source=RouteDecisionSource.MODEL_CATALOG,
            capability_source=model.capability_source,
        )
    elif supports_messages:
        decision = RouteDecision(
            protocol_leg=ProtocolLeg.MESSAGES,
            reason=RouteDecisionReason.SINGLE_CAPABILITY,
            source=RouteDecisionSource.MODEL_CATALOG,
            capability_source=model.capability_source,
        )
    elif supports_responses:
        decision = RouteDecision(
            protocol_leg=ProtocolLeg.RESPONSES,
            reason=RouteDecisionReason.SINGLE_CAPABILITY,
            source=RouteDecisionSource.MODEL_CATALOG,
            capability_source=model.capability_source,
        )
    else:
        raise RouteDecisionError(
            RouteDecisionErrorCode.CAPABILITY_MISSING,
            resolved_model=model.resolved_model,
            detail="model does not advertise Messages or Responses capability",
        )

    return _require_transport(model, transports, decision)


def _validated_endpoints(model: ResolvedModelFacts) -> frozenset[str]:
    if not model.resolved_model:
        raise RouteDecisionError(
            RouteDecisionErrorCode.MODEL_NOT_FOUND,
            resolved_model=model.resolved_model,
            detail="resolved model id is empty",
        )
    if not model.supported_endpoints:
        raise RouteDecisionError(
            RouteDecisionErrorCode.CAPABILITY_MISSING,
            resolved_model=model.resolved_model,
            detail="supported_endpoints is missing or empty",
        )
    if model.capability_conflict is not None:
        raise RouteDecisionError(
            RouteDecisionErrorCode.CAPABILITY_CONFLICT,
            resolved_model=model.resolved_model,
            detail=model.capability_conflict,
        )

    endpoints = frozenset(model.supported_endpoints)
    return endpoints


def _supports_leg(
    leg: ProtocolLeg,
    supports_messages: bool,
    supports_responses: bool,
) -> bool:
    if leg is ProtocolLeg.MESSAGES:
        return supports_messages
    return supports_responses


def _require_transport(
    model: ResolvedModelFacts,
    transports: TransportAvailability,
    decision: RouteDecision,
) -> RouteDecision:
    if transports.supports(decision.protocol_leg):
        return decision
    raise RouteDecisionError(
        RouteDecisionErrorCode.TRANSPORT_UNAVAILABLE,
        resolved_model=model.resolved_model,
        detail=f"no physical transport is available for {decision.protocol_leg.value}",
    )


__all__ = [
    "ProtocolLeg",
    "ResolvedModelFacts",
    "RouteDecision",
    "RouteDecisionError",
    "RouteDecisionErrorCode",
    "RouteDecisionReason",
    "RouteDecisionSource",
    "TransportAvailability",
    "decide_protocol_leg",
]