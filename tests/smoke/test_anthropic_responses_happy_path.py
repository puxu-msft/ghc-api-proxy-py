from collections.abc import Mapping

import pytest

from app.anthropic.request_preparation import prepare_anthropic_request
from app.anthropic.thinking.responses_reasoning import (
    anthropic_thinking_to_responses,
)
from app.openai.responses_stream_parser import (
    CompletedBlock,
    ReasoningBlock,
    ResponsesStreamParser,
)
from app.pipeline.route_policy import (
    ProtocolLeg,
    ResolvedModelFacts,
    RouteDecisionError,
    RouteDecisionErrorCode,
    TransportAvailability,
    decide_protocol_leg,
)
from app.protocols.responses_anthropic import (
    convert_responses_response_to_anthropic,
)

ALL_TRANSPORTS = TransportAvailability(
    messages_http=True,
    responses_http=True,
    responses_websocket=True,
)
PROJECT_V1_OPAQUE_SIGNATURE = (
    "ghc-api-proxy:synthetic-reasoning:v1:"
    "eyJ0YWciOiJvcGVuYWkucmVzcG9uc2VzLnJlYXNvbmluZy5lbmNyeXB0ZWRfY29udGVudCIs"
    "ImVuY3J5cHRlZF9jb250ZW50Ijoib3BhcXVlLfCfmIAifQ"
)


def test_direct_messages_strips_static_proxy_carrier_vectors() -> None:
    prepared = prepare_anthropic_request(
        {
            "model": "claude-test",
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "project",
                            "signature": PROJECT_V1_OPAQUE_SIGNATURE,
                        },
                        {
                            "type": "thinking",
                            "thinking": "upstream",
                            "signature": "copilot-api:synthetic-reasoning:v1:RU5D",
                        },
                        {
                            "type": "thinking",
                            "thinking": "native",
                            "signature": "native-anthropic-signature",
                        },
                        {"type": "text", "text": "answer"},
                    ],
                }
            ],
        },
        apply_payload_rewrites=False,
    )

    assert prepared.wire["messages"][0]["content"] == [
        {
            "type": "thinking",
            "thinking": "native",
            "signature": "native-anthropic-signature",
        },
        {"type": "text", "text": "answer"},
    ]


def test_nonstream_reasoning_uses_static_project_v1_vector_and_public_reverse() -> None:
    reasoning: Mapping[str, object] = {
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": "visible"}],
        "encrypted_content": "opaque-😀",
    }
    response: Mapping[str, object] = {
        "id": "resp_reasoning",
        "model": "gpt-test",
        "status": "completed",
        "output": [reasoning],
    }

    converted = convert_responses_response_to_anthropic(response)
    (block,) = converted.message.content

    assert (block.type, block.thinking) == ("thinking", "visible")
    assert block.signature == PROJECT_V1_OPAQUE_SIGNATURE
    assert anthropic_thinking_to_responses(block.model_dump(mode="python")) == reasoning


def test_nonstream_usage_keeps_reasoning_and_future_details_as_typed_facts() -> None:
    converted = convert_responses_response_to_anthropic(
        {
            "id": "resp_usage",
            "model": "gpt-test",
            "status": "completed",
            "output": [],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 30,
                "total_tokens": 130,
                "input_tokens_details": {
                    "cached_tokens": 20,
                    "cache_write_tokens": 10,
                },
                "output_tokens_details": {
                    "reasoning_tokens": 12,
                    "accepted_prediction_tokens": 5,
                },
            },
        }
    )

    assert converted.message.usage is not None
    assert converted.message.usage.model_dump() == {
        "input_tokens": 70,
        "output_tokens": 30,
        "cache_creation_input_tokens": 10,
        "cache_read_input_tokens": 20,
    }
    assert converted.usage_facts is not None
    assert converted.usage_facts.reasoning_tokens == 12
    assert converted.usage_facts.output_tokens_details == {
        "reasoning_tokens": 12,
        "accepted_prediction_tokens": 5,
    }


def test_stream_parser_reasoning_payload_feeds_the_project_carrier() -> None:
    parser = ResponsesStreamParser()
    parser.process(
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {
                "id": "rs_0",
                "type": "reasoning",
                "summary": [],
                "encrypted_content": "draft",
            },
        }
    )

    (completed,) = parser.process(
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "id": "rs_0",
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "visible"}],
                "encrypted_content": "authoritative",
            },
        }
    )

    assert isinstance(completed, CompletedBlock)
    assert isinstance(completed.content, ReasoningBlock)
    assert completed.content == ReasoningBlock("visible", "authoritative")


@pytest.mark.parametrize(
    ("override", "endpoints", "expected"),
    [
        (None, ["/v1/messages", "/responses"], ProtocolLeg.MESSAGES),
        (None, ["/v1/messages"], ProtocolLeg.MESSAGES),
        (None, ["/responses"], ProtocolLeg.RESPONSES),
        (ProtocolLeg.RESPONSES, ["/v1/messages", "/responses"], ProtocolLeg.RESPONSES),
    ],
)
def test_route_truth_table_selects_the_expected_protocol_leg(
    override: ProtocolLeg | None,
    endpoints: list[str],
    expected: ProtocolLeg,
) -> None:
    decision = decide_protocol_leg(
        ResolvedModelFacts("resolved-model", endpoints),
        override=override,
        transports=ALL_TRANSPORTS,
    )

    assert decision.protocol_leg is expected


def test_route_truth_table_fails_closed_for_unknown_capability() -> None:
    with pytest.raises(RouteDecisionError) as caught:
        decide_protocol_leg(
            ResolvedModelFacts("unknown-model", []),
            transports=ALL_TRANSPORTS,
        )

    assert caught.value.code is RouteDecisionErrorCode.CAPABILITY_MISSING