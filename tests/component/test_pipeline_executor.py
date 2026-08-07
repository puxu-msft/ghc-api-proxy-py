from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

import httpx
import pytest

from app.anthropic.client import AnthropicClient
from app.config.settings import AppSettings
from app.errors import ApiError
from app.hooks.context import HookContext
from app.hooks.executor import HooksExecutor
from app.hooks.registry import HookRegistryBuilder
from app.hooks.types import ObserverEvent
from app.models.anthropic import MessagesRequest
from app.pipeline.context import RequestContext, RequestState
from app.pipeline.executor import UpstreamResponseError, execute_anthropic_pipeline
from app.transform.model_resolver import ModelResolver
from app.upstream.models_api import ModelCatalog


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


@dataclass(slots=True)
class RecordingHistory:
    started_contexts: list[RequestContext] = field(
        default_factory=lambda: list[RequestContext]()
    )
    finalized_contexts: list[RequestContext] = field(
        default_factory=lambda: list[RequestContext]()
    )

    async def started(self, context: RequestContext) -> None:
        self.started_contexts.append(context)

    async def finalized(
        self,
        context: RequestContext,
        *,
        response: dict[str, Any] | None = None,
    ) -> None:
        del response
        self.finalized_contexts.append(context)


@dataclass(slots=True)
class RecordingObserver:
    name: str = "component-recorder"
    order: int = 1001
    events: frozenset[ObserverEvent] = frozenset(ObserverEvent)
    seen: list[ObserverEvent] = field(
        default_factory=lambda: list[ObserverEvent]()
    )

    async def observe(
        self,
        event: ObserverEvent,
        context: HookContext,
        data: Mapping[str, Any],
    ) -> None:
        del context, data
        self.seen.append(event)


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


@pytest.mark.asyncio
async def test_pre_attempt_preparation_failure_observes_terminal_lifecycle_once() -> None:
    catalog = ModelCatalog(None, "https://upstream.test")
    catalog.replace_from_data(
        {
            "object": "list",
            "data": [
                {
                    "id": "claude-test",
                    "vendor": "test",
                    "supported_endpoints": [],
                }
            ],
        }
    )
    history = RecordingHistory()
    observer = RecordingObserver()
    builder = HookRegistryBuilder()
    builder.register_observer(observer)
    client = AnthropicClient(
        Target(200),
        ModelResolver(available_ids={"claude-test"}, model_overrides={}),
        AppSettings(),
        history=cast(Any, history),
        hooks=HooksExecutor(builder.build(), user_timeout_ms=1_000),
        model_catalog=catalog,
    )

    with pytest.raises(ApiError) as captured:
        await execute_anthropic_pipeline(client, _request())

    assert captured.value.code == "capability_missing"
    assert history.finalized_contexts == history.started_contexts
    context = history.finalized_contexts[0]
    assert context.state is RequestState.FAILED
    assert context.attempts == []
    assert observer.seen == [
        ObserverEvent.REQUEST_RECEIVED,
        ObserverEvent.ERROR,
        ObserverEvent.FINALIZE,
    ]