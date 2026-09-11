from typing import Any

import pytest

from app.pipeline.request import WireFormat
from app.pipeline.translation_driver.registry import default_registry
from app.pipeline.translation_driver.usage import (
    ResponsesUsageError,
    convert_responses_usage,
)


def test_responses_response_gets_an_anthropic_public_id() -> None:
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
    assert semantic.model == "gpt-test"


def test_responses_usage_codec_is_shared_and_preserves_exact_details() -> None:
    converted = convert_responses_usage(
        {
            "input_tokens": 100,
            "output_tokens": 30,
            "total_tokens": 130,
            "input_tokens_details": {
                "cached_tokens": 20,
                "cache_write_tokens": 10,
                "audio_tokens": 3,
            },
            "output_tokens_details": {"reasoning_tokens": 12},
        }
    )

    assert converted.wire.model_dump() == {
        "input_tokens": 70,
        "output_tokens": 30,
        "cache_creation_input_tokens": 10,
        "cache_read_input_tokens": 20,
    }
    assert converted.exact is not None
    assert converted.exact.input_tokens_details["audio_tokens"] == 3
    assert converted.exact.reasoning_tokens == 12
    assert converted.facts == ()


def test_responses_usage_codec_rejects_malformed_values_at_the_wire_seam() -> None:
    malformed: dict[str, Any] = {
        "input_tokens": 1,
        "output_tokens": 1,
        "input_tokens_details": {"cached_tokens": True},
    }

    with pytest.raises(ResponsesUsageError) as caught:
        convert_responses_usage(malformed)
    assert caught.value.code == "invalid_usage"
    assert caught.value.field_path == "usage.input_tokens_details.cached_tokens"
