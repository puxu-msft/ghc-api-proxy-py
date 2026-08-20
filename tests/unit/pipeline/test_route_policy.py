import pytest

from app.pipeline.route_policy import (
    ProtocolLeg,
    ResolvedModelFacts,
    RouteDecisionError,
    RouteDecisionErrorCode,
    RouteDecisionReason,
    RouteDecisionSource,
    TransportAvailability,
    decide_protocol_leg,
)

ALL_TRANSPORTS = TransportAvailability(
    messages_http=True,
    responses_http=True,
    responses_websocket=True,
)


@pytest.mark.parametrize(
    ("endpoints", "expected_leg", "expected_reason"),
    [
        (
            ["/v1/messages", "/responses"],
            ProtocolLeg.MESSAGES,
            RouteDecisionReason.DUAL_CAPABILITY_DEFAULT,
        ),
        (["/v1/messages"], ProtocolLeg.MESSAGES, RouteDecisionReason.SINGLE_CAPABILITY),
        (["/responses"], ProtocolLeg.RESPONSES, RouteDecisionReason.SINGLE_CAPABILITY),
        (["ws:/responses"], ProtocolLeg.RESPONSES, RouteDecisionReason.SINGLE_CAPABILITY),
    ],
)
def test_automatic_route_truth_table(
    endpoints: list[str],
    expected_leg: ProtocolLeg,
    expected_reason: RouteDecisionReason,
) -> None:
    decision = decide_protocol_leg(
        ResolvedModelFacts("resolved-model", endpoints),
        transports=ALL_TRANSPORTS,
    )

    assert decision.protocol_leg is expected_leg
    assert decision.reason is expected_reason
    assert decision.source is RouteDecisionSource.MODEL_CATALOG


def test_explicit_override_wins_after_capability_gate() -> None:
    decision = decide_protocol_leg(
        ResolvedModelFacts("dual-model", ["/v1/messages", "/responses"]),
        override=ProtocolLeg.RESPONSES,
        transports=ALL_TRANSPORTS,
    )

    assert decision.protocol_leg is ProtocolLeg.RESPONSES
    assert decision.reason is RouteDecisionReason.EXPLICIT_OVERRIDE
    assert decision.source is RouteDecisionSource.ROUTE_OVERRIDE


def test_unsupported_override_fails_without_falling_through() -> None:
    with pytest.raises(RouteDecisionError) as caught:
        decide_protocol_leg(
            ResolvedModelFacts("messages-only", ["/v1/messages"]),
            override=ProtocolLeg.RESPONSES,
            transports=ALL_TRANSPORTS,
        )

    assert caught.value.code is RouteDecisionErrorCode.OVERRIDE_UNSUPPORTED


@pytest.mark.parametrize(
    ("model", "expected_code"),
    [
        (None, RouteDecisionErrorCode.MODEL_NOT_FOUND),
        (ResolvedModelFacts("missing", None), RouteDecisionErrorCode.CAPABILITY_MISSING),
        (ResolvedModelFacts("empty", []), RouteDecisionErrorCode.CAPABILITY_MISSING),
        (
            ResolvedModelFacts("chat-only", ["/chat/completions"]),
            RouteDecisionErrorCode.CAPABILITY_MISSING,
        ),
        (
            ResolvedModelFacts(
                "conflict",
                ["/v1/messages", "/responses"],
                capability_conflict="catalog capability sources disagree",
            ),
            RouteDecisionErrorCode.CAPABILITY_CONFLICT,
        ),
    ],
)
def test_unknown_missing_and_conflicting_capabilities_fail_closed(
    model: ResolvedModelFacts | None,
    expected_code: RouteDecisionErrorCode,
) -> None:
    with pytest.raises(RouteDecisionError) as caught:
        decide_protocol_leg(model, transports=ALL_TRANSPORTS)

    assert caught.value.code is expected_code


def test_selected_leg_transport_unavailable_does_not_change_protocol() -> None:
    with pytest.raises(RouteDecisionError) as caught:
        decide_protocol_leg(
            ResolvedModelFacts("dual-model", ["/v1/messages", "ws:/responses"]),
            transports=TransportAvailability(responses_http=True),
        )

    assert caught.value.code is RouteDecisionErrorCode.TRANSPORT_UNAVAILABLE
    assert "messages" in caught.value.detail


def test_override_transport_unavailable_does_not_fall_through() -> None:
    with pytest.raises(RouteDecisionError) as caught:
        decide_protocol_leg(
            ResolvedModelFacts("dual-model", ["/v1/messages", "/responses"]),
            override=ProtocolLeg.RESPONSES,
            transports=TransportAvailability(messages_http=True),
        )

    assert caught.value.code is RouteDecisionErrorCode.TRANSPORT_UNAVAILABLE
    assert "responses" in caught.value.detail


def test_websocket_advertisement_proves_responses_without_forcing_websocket() -> None:
    decision = decide_protocol_leg(
        ResolvedModelFacts("ws-advertised", ["ws:/responses"]),
        transports=TransportAvailability(responses_http=True),
    )

    assert decision.protocol_leg is ProtocolLeg.RESPONSES
