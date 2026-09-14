import json
from typing import Any

from app.pipeline.delivery.assembling import Terminal
from app.pipeline.delivery.formats.anthropic_messages import AnthropicFramer
from app.pipeline.delivery.formats.openai_responses import ResponsesAssembler
from app.pipeline.delivery.sse_source import SseEvent
from app.pipeline.request import WireFormat
from app.pipeline.translation_driver.registry import default_registry
from app.pipeline.translation_driver.semantic import LossCode
from app.pipeline.translation_driver.usage import convert_responses_usage
from tests.unit.pipeline.responses_sdk import (
    validate_responses_request,
    validate_responses_response,
    validate_responses_stream_event,
)


def test_anthropic_images_and_documents_become_sdk_responses_content_parts() -> None:
    payload, semantic = default_registry().translate(
        {
            "model": "m",
            "max_tokens": 32,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "inspect these"},
                        {
                            "type": "image",
                            "source": {"type": "url", "url": "https://example.test/a.png"},
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": "abc",
                            },
                        },
                        {
                            "type": "document",
                            "name": "notes.pdf",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": "pdf",
                            },
                        },
                    ],
                }
            ],
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )

    assert payload["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": "inspect these"},
                {
                    "type": "input_image",
                    "detail": "auto",
                    "image_url": "https://example.test/a.png",
                },
                {
                    "type": "input_image",
                    "detail": "auto",
                    "image_url": "data:image/png;base64,abc",
                },
                {
                    "type": "input_file",
                    "file_data": "data:application/pdf;base64,pdf",
                    "filename": "notes.pdf",
                },
            ],
        },
    ]
    validate_responses_request(payload)
    assert not semantic.conversion.has(LossCode.IMAGE_SOURCE_COERCED)


def test_tool_result_preserves_text_image_and_file_parts() -> None:
    payload, semantic = default_registry().translate(
        {
            "model": "m",
            "max_tokens": 32,
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call-1",
                            "name": "inspect",
                            "input": {},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call-1",
                            "content": [
                                {"type": "text", "text": "visible"},
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": "abc",
                                    },
                                },
                                {
                                    "type": "document",
                                    "source": {
                                        "type": "file",
                                        "file_id": "file-1",
                                    },
                                },
                            ],
                        }
                    ],
                },
            ],
        },
        source=WireFormat.ANTHROPIC_MESSAGES,
        target=WireFormat.OPENAI_RESPONSES,
    )

    sdk_payload = validate_responses_request(payload)
    output = sdk_payload["input"][1]
    assert output == {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": [
            {"type": "input_text", "text": "visible"},
            {
                "type": "input_image",
                "detail": "auto",
                "image_url": "data:image/png;base64,abc",
            },
            {"type": "input_file", "file_id": "file-1"},
        ],
    }
    assert not semantic.conversion.has(LossCode.TOOL_RESULT_CONTENT_FLATTENED)


def test_responses_images_round_trip_to_anthropic_images() -> None:
    payload, semantic = default_registry().translate_response(
        {
            "id": "resp-image",
            "model": "gpt-test",
            "status": "completed",
            "output": [
                {
                    "type": "image_generation_call",
                    "id": "ig-1",
                    "status": "completed",
                    "result": "generated",
                },
            ],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )

    assert payload["content"] == [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "generated"},
        },
    ]
    assert semantic.conversion.has(LossCode.IMAGE_MEDIA_TYPE_ASSUMED)


def test_responses_image_generation_item_survives_same_format_round_trip() -> None:
    payload, semantic = default_registry().translate_response(
        {
            "id": "resp-image-same",
            "model": "gpt-test",
            "status": "completed",
            "output": [
                {
                    "type": "image_generation_call",
                    "id": "ig-1",
                    "status": "completed",
                    "result": "generated",
                }
            ],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.OPENAI_RESPONSES,
    )
    validate_responses_response(payload)

    assert payload["output"] == [
        {
            "type": "image_generation_call",
            "id": "ig-1",
            "status": "completed",
            "result": "generated",
        }
    ]
    assert semantic.conversion.lossless


def test_top_level_responses_images_and_documents_become_sdk_content_parts() -> None:
    payload, semantic = default_registry().translate(
        {
            "model": "m",
            "input": [
                {
                    "type": "image",
                    "source": {"type": "url", "url": "https://example.test/a.png"},
                },
                {
                    "type": "document",
                    "title": "report.pdf",
                    "source": {
                        "type": "file",
                        "file_id": "file-1",
                    },
                },
            ],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.OPENAI_RESPONSES,
    )

    validate_responses_request(payload)
    assert payload["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_image",
                    "detail": "auto",
                    "image_url": "https://example.test/a.png",
                }
            ],
        },
        {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_file",
                    "file_id": "file-1",
                    "filename": "report.pdf",
                }
            ],
        },
    ]
    assert semantic.conversion.lossless


def test_streamed_image_generation_item_becomes_anthropic_image_block() -> None:
    assembler = ResponsesAssembler()
    added = {
        "type": "response.output_item.added",
        "sequence_number": 0,
        "output_index": 0,
        "item": {"type": "image_generation_call", "id": "ig-1", "status": "in_progress"},
    }
    done = {
        "type": "response.output_item.done",
        "sequence_number": 1,
        "output_index": 0,
        "item": {
            "type": "image_generation_call",
            "id": "ig-1",
            "status": "completed",
            "result": "generated",
        },
    }
    validate_responses_stream_event(added)
    validate_responses_stream_event(done)
    assembler.push(
        SseEvent(
            "response.output_item.added",
            json.dumps(added),
        )
    )
    blocks = assembler.push(
        SseEvent(
            "response.output_item.done",
            json.dumps(done),
        )
    )

    assert len(blocks) == 1
    assert blocks[0].kind == "image"
    assert blocks[0].payload == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "generated"},
    }


def test_responses_tool_result_parts_return_to_anthropic_content_blocks() -> None:
    payload, semantic = default_registry().translate(
        {
            "model": "m",
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": [
                        {"type": "input_text", "text": "visible"},
                        {
                            "type": "input_image",
                            "detail": "auto",
                            "image_url": "data:image/png;base64,abc",
                        },
                        {"type": "input_file", "file_id": "file-1", "filename": "a.pdf"},
                    ],
                }
            ],
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )

    assert payload["messages"] == [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call-1",
                    "content": [
                        {"type": "text", "text": "visible"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": "abc",
                            },
                        },
                        {
                            "type": "document",
                            "source": {"type": "file", "file_id": "file-1"},
                            "title": "a.pdf",
                        },
                    ],
                }
            ],
        }
    ]
    assert semantic.conversion.lossless


def test_usage_conversion_preserves_aliases_and_best_effort_valid_fields() -> None:
    converted = convert_responses_usage(
        {
            "input_tokens": 100,
            "output_tokens": 30,
            "cache_read_input_tokens": 20,
            "cache_creation_input_tokens": 10,
            "reasoning_tokens": 12,
        }
    )
    assert converted.wire.model_dump() == {
        "input_tokens": 70,
        "output_tokens": 30,
        "cache_creation_input_tokens": 10,
        "cache_read_input_tokens": 20,
    }
    assert converted.exact is not None
    assert converted.exact.reasoning_tokens == 12

    malformed: dict[str, Any] = {
        "input_tokens": 100,
        "output_tokens": 30,
        "input_tokens_details": {"cached_tokens": True, "cache_write_tokens": 10},
    }
    best_effort = convert_responses_usage(malformed, strict=False)
    assert best_effort.wire.model_dump() == {
        "input_tokens": 90,
        "output_tokens": 30,
        "cache_creation_input_tokens": 10,
        "cache_read_input_tokens": 0,
    }
    assert any(fact.code == "usage_malformed" for fact in best_effort.facts)


def test_response_usage_projection_records_malformed_fields_without_erasing_valid_counts() -> None:
    payload, semantic = default_registry().translate_response(
        {
            "id": "resp-usage",
            "model": "gpt-test",
            "status": "completed",
            "output": [],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 30,
                "input_tokens_details": {
                    "cached_tokens": True,
                    "cache_write_tokens": 10,
                },
            },
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )

    assert payload["usage"] == {
        "input_tokens": 90,
        "output_tokens": 30,
        "cache_creation_input_tokens": 10,
        "cache_read_input_tokens": 0,
    }
    assert semantic.conversion.has(LossCode.USAGE_MALFORMED)


def test_response_usage_projection_keeps_usage_unknown_when_core_count_is_malformed() -> None:
    payload, semantic = default_registry().translate_response(
        {
            "id": "resp-usage-bad",
            "model": "gpt-test",
            "status": "completed",
            "output": [],
            "usage": {
                "input_tokens": "100",
                "output_tokens": 30,
            },
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )

    assert payload["usage"] == {}
    assert semantic.conversion.has(LossCode.USAGE_MALFORMED)


def test_stream_usage_malformed_does_not_use_missing_usage_zero_fallback() -> None:
    from app.pipeline.translation_driver.responses_terminal import terminal_facts_from_event

    facts = terminal_facts_from_event(
        "response.completed",
        {"response": {"usage": {"input_tokens": "100", "output_tokens": 30}}},
        saw_tool_call=False,
    )
    assert facts is not None
    assert facts.usage == {}
    assert facts.usage_present is True
    assert facts.usage_malformed is True

    terminal = Terminal(
        stop_reason="end_turn",
        seen=True,
        usage=facts.usage,
        usage_present=facts.usage_present,
        usage_malformed=facts.usage_malformed,
    )
    frames = AnthropicFramer(message_id="m", model="m").terminal(terminal)
    message_delta = next(
        json.loads(frame.split(b"data: ", 1)[1])
        for frame in frames
        if frame.startswith(b"event: message_delta")
    )
    assert message_delta["usage"] == {}


def test_non_object_usage_is_malformed_not_missing() -> None:
    payload, semantic = default_registry().translate_response(
        {
            "id": "resp-usage-shape",
            "model": "gpt-test",
            "status": "completed",
            "output": [],
            "usage": "not-an-object",
        },
        source=WireFormat.OPENAI_RESPONSES,
        target=WireFormat.ANTHROPIC_MESSAGES,
    )
    assert payload["usage"] == {}
    assert semantic.conversion.has(LossCode.USAGE_MALFORMED)

    from app.pipeline.translation_driver.responses_terminal import terminal_facts_from_event

    facts = terminal_facts_from_event(
        "response.completed",
        {"response": {"usage": "not-an-object"}},
        saw_tool_call=False,
    )
    assert facts is not None
    assert facts.usage_present is True
    assert facts.usage_malformed is True
