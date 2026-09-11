from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.pipeline.handled import HandledRequest
from app.pipeline.reply import (
    RESPONSE_CONVERSION_LOSSES,
    RESPONSE_CONVERSION_OPAQUE_PAYLOADS,
    RESPONSE_CONVERSION_WARNINGS,
    response_payload,
)
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.translation_driver.registry import default_registry
from app.pipeline.translation_driver.responses_items import (
    ResponsesItemContext,
    normalize_response_item,
)
from app.pipeline.translation_driver.responses_terminal import terminal_facts_from_event
from app.pipeline.translation_driver.semantic import Conversion, LossCode


def test_buffered_responses_response_uses_an_anthropic_public_id() -> None:
    payload, semantic = default_registry().translate_response(
        {
            "id": "resp_123",
            "model": "gpt-test",
            "status": "completed",
            "output": [],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )

    assert payload["id"] == "msg_HAGUmRojzlDCLGp3XE8QLxwLG9FislDW"
    assert semantic.upstream_id == "resp_123"
    assert semantic.upstream_model == "gpt-test"


def test_response_item_normalizer_preserves_message_part_cardinality() -> None:
    conversion = Conversion()
    role, blocks = normalize_response_item(
        {
            "type": "message",
            "content": [
                {"type": "output_text", "text": "one"},
                {"type": "output_text", "text": "two"},
            ],
        },
        context=ResponsesItemContext(),
        conversion=conversion,
    )

    assert role == "user"
    assert [block.text for block in blocks] == ["one", "two"]
    assert conversion.lossless


def test_buffered_unknown_output_item_is_opaque_and_warns_when_skipped() -> None:
    payload, semantic = default_registry().translate_response(
        {
            "id": "resp_unknown",
            "model": "gpt-test",
            "status": "completed",
            "output": [{"type": "future_output_item"}],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )

    assert payload["content"] == []
    assert semantic.opaque_payloads[0].source_format == "openai-responses"
    assert semantic.conversion.warnings[0].field_path == "output[0]"
    assert not semantic.conversion.lossless
    assert semantic.conversion.has(LossCode.OPAQUE_RESPONSE_SKIPPED)
    assert payload["stop_reason"] == "incomplete"


def test_same_format_round_trip_retains_opaque_output_without_diagnostics() -> None:
    payload, semantic = default_registry().translate_response(
        {
            "id": "resp_unknown",
            "model": "gpt-test",
            "status": "completed",
            "output": [{"type": "future_output_item", "value": 1}],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.OPENAI_RESPONSES,
    )

    assert payload["output"] == [{"type": "future_output_item", "value": 1}]
    assert semantic.conversion.losses == []
    assert semantic.conversion.warnings == []


def test_response_diagnostics_are_absorbed_on_the_handled_context() -> None:
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="m",
        payload={},
    )
    handled = cast(
        HandledRequest,
        SimpleNamespace(
            synthesized=False,
            route=SimpleNamespace(
                translation_required=True,
                target_format=WireFormat.OPENAI_RESPONSES,
                inbound_format=WireFormat.ANTHROPIC_MESSAGES,
            ),
            context=context,
        ),
    )
    chain = cast(
        Any,
        SimpleNamespace(
            translators=default_registry(),
            config=SimpleNamespace(
                upstream_request_retry=SimpleNamespace(
                    hand_over_stop_reasons=frozenset({"max_tokens"})
                )
            ),
        ),
    )

    translated = response_payload(
        chain,
        handled,
        {
            "id": "resp_unknown",
            "model": "gpt-test",
            "status": "completed",
            "output": [{"type": "future_output_item"}],
        },
    )

    assert translated["content"] == []
    assert context.extras[RESPONSE_CONVERSION_LOSSES]
    assert context.extras[RESPONSE_CONVERSION_WARNINGS]
    assert context.extras[RESPONSE_CONVERSION_OPAQUE_PAYLOADS]


def test_buffered_incomplete_tool_call_defers_malformed_arguments_to_terminal() -> None:
    payload, _ = default_registry().translate_response(
        {
            "id": "resp_incomplete",
            "model": "gpt-test",
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [
                {
                    "type": "function_call",
                    "call_id": "c0",
                    "name": "Bash",
                    "arguments": "{not json",
                    "status": "incomplete",
                }
            ],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )

    assert payload["stop_reason"] == "max_tokens"
    assert payload["content"][0]["input"] == {"__raw": "{not json"}


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("response.incomplete", "max_tokens"),
        ("response.incomplete", "incomplete"),
        ("response.completed", "end_turn"),
    ],
)
def test_terminal_normalizer_uses_event_kind_when_status_is_absent(
    kind: str,
    expected: str,
) -> None:
    data: dict[str, object] = (
        {"response": {"incomplete_details": {"reason": "max_output_tokens"}}}
        if expected == "max_tokens"
        else {"response": {}}
    )

    facts = terminal_facts_from_event(kind, data, saw_tool_call=False)

    assert facts is not None
    assert facts.stop_reason == expected
