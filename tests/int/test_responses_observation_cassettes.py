from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import orjson
import pytest

from app.pipeline.delivery.sse_source import read_events
from app.pipeline.response_action import ClientActionRequirement
from app.pipeline.response_observation import (
    JsonAvailability,
    ResponseObservation,
    ResponsesObserver,
    thaw_json,
)

CASSETTE_DIR = Path(__file__).parent / "cassettes"


def _interaction(name: str, *, stream: bool) -> dict[str, Any]:
    cassette = cast(
        dict[str, Any],
        orjson.loads((CASSETTE_DIR / f"{name}.json").read_bytes()),
    )
    interaction = next(
        cast(dict[str, Any], raw)
        for raw in cast(list[Any], cassette["interactions"])
        if "responses" in cast(dict[str, Any], raw)["request"]["path"]
        and cast(dict[str, Any], raw)["request"]["shape"]["stream"] is stream
    )
    assert interaction["response"]["source"] == "live-recording"
    return interaction


async def _chunks(interaction: dict[str, Any]) -> AsyncIterator[bytes]:
    for chunk in cast(list[dict[str, str]], interaction["response"]["chunks"]):
        yield chunk["text"].encode()


def _assert_web_search_ground_truth(observed: ResponseObservation) -> None:
    assert observed.status == "completed"
    assert observed.model == "gpt-5.5-2026-04-23"
    assert observed.service_tier == "default"
    assert observed.output_items is not None
    assert [item.type for item in observed.output_items] == ["web_search_call", "message"]
    assert [item.client_action.requirement for item in observed.output_items] == [
        ClientActionRequirement.NOT_REQUIRED,
        ClientActionRequirement.NOT_REQUIRED,
    ]

    usage = observed.usage
    assert usage is not None
    assert usage.normalized.input_tokens == 981
    assert usage.normalized.cache_read_input_tokens == 3712
    assert usage.normalized.cache_creation_input_tokens == 0
    assert usage.normalized.output_tokens == 112
    assert usage.exact is not None
    assert usage.exact.upstream_input_tokens == 4693
    assert usage.exact.reasoning_tokens == 51
    assert usage.exact.computed_total_tokens == 4805
    assert usage.exact.upstream_total_tokens == 4805
    assert usage.raw.value is not None
    raw_usage = cast(dict[str, Any], thaw_json(usage.raw.value))
    assert raw_usage["input_tokens"] == 4693
    assert raw_usage["input_tokens_details"] == {
        "cached_tokens": 3712,
        "cache_write_tokens": 0,
    }
    assert raw_usage["output_tokens"] == 112
    assert raw_usage["output_tokens_details"] == {"reasoning_tokens": 51}
    assert raw_usage["total_tokens"] == 4805

    assert observed.provider_usage.value is not None
    provider_usage = cast(dict[str, Any], thaw_json(observed.provider_usage.value))
    assert provider_usage["total_nano_aiu"] == 1012100000
    assert observed.tool_usage.value is not None
    tool_usage = cast(dict[str, Any], thaw_json(observed.tool_usage.value))
    assert tool_usage["web_search"]["num_requests"] == 1


@pytest.mark.asyncio
async def test_live_web_search_stream_and_body_are_both_faithful_before_parity() -> None:
    stream_interaction = _interaction("responses_web_search_stream", stream=True)
    body_interaction = _interaction("responses_web_search_nonstream", stream=False)
    streamed = ResponsesObserver()
    buffered = ResponsesObserver()

    async for event in read_events(_chunks(stream_interaction)):
        streamed.observe_event(event)
    body_text = "".join(
        chunk["text"]
        for chunk in cast(list[dict[str, str]], body_interaction["response"]["chunks"])
    )
    body = cast(dict[str, Any], orjson.loads(body_text))
    buffered.observe_response(body)

    streamed_observation = streamed.snapshot()
    buffered_observation = buffered.snapshot()
    # Each side first has to match the independent recording. Equality alone would pass if a shared parser dropped the same field twice.
    _assert_web_search_ground_truth(streamed_observation)
    _assert_web_search_ground_truth(buffered_observation)
    assert streamed_observation.error.availability is JsonAvailability.EXPLICIT_NULL
    assert buffered_observation.error.availability is JsonAvailability.ABSENT
    # The wire spelling remains visible, while the semantic parity assertion normalises only the independently checked no-error representation.
    assert replace(
        streamed_observation,
        error=buffered_observation.error,
    ) == buffered_observation
