from collections.abc import AsyncIterator, Mapping
from typing import Any

import httpx
import pytest

from app.anthropic.client import AnthropicClient
from app.models.anthropic import MessagesRequest
from app.pipeline.context import RequestState
from app.pipeline.executor import UpstreamResponseError, execute_anthropic_pipeline
from app.transform.model_resolver import ModelResolver


class Stream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"data: event\n\n"


class Target:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    async def send_anthropic(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        del payload, stream, extra_headers
        return httpx.Response(
            self.status_code,
            request=httpx.Request("POST", "https://upstream.test/v1/messages"),
            stream=Stream(),
        )


def _request(*, stream: bool = False) -> MessagesRequest:
    return MessagesRequest.model_validate(
        {
            "model": "claude-test",
            "max_tokens": 100,
            "stream": stream,
            "messages": [{"role": "user", "content": "hello"}],
        }
    )


@pytest.mark.asyncio
async def test_execute_pipeline_success_tracks_attempt_and_state() -> None:
    client = AnthropicClient(
        Target(200),
        ModelResolver(available_ids={"claude-test"}, model_overrides={}),
    )

    result = await execute_anthropic_pipeline(client, _request())

    assert result.context.state is RequestState.COMPLETED
    assert result.context.attempts[0].status_code == 200
    assert result.context.resolved_model == "claude-test"
    await result.response.aclose()


@pytest.mark.asyncio
async def test_execute_pipeline_stream_enters_streaming_state() -> None:
    client = AnthropicClient(
        Target(200),
        ModelResolver(available_ids={"claude-test"}, model_overrides={}),
    )

    result = await execute_anthropic_pipeline(client, _request(stream=True))

    assert result.context.state is RequestState.STREAMING
    await result.response.aclose()


@pytest.mark.asyncio
async def test_execute_pipeline_failure_records_error_and_closes_response() -> None:
    client = AnthropicClient(
        Target(400),
        ModelResolver(available_ids={"claude-test"}, model_overrides={}),
    )

    with pytest.raises(UpstreamResponseError) as captured:
        await execute_anthropic_pipeline(client, _request())

    assert captured.value.context.state is RequestState.FAILED
    assert captured.value.context.attempts[0].status_code == 400