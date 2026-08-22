from collections.abc import AsyncIterator
from typing import Any, Protocol

import httpx2
from fastapi.testclient import TestClient

from app.config.settings import AppSettings
from app.deps import get_anthropic_client, get_token_counter
from app.models.anthropic import MessagesRequest
from app.pipeline.context import Attempt, RequestContext, RequestState
from app.pipeline.executor import PipelineResult, UpstreamResponseError
from app.server.app_factory import create_app


class BytesStream(httpx2.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b'event: message_stop\ndata: {"type":"message_stop"}\n\n'


class StubAnthropicClient:
    def __init__(self, *, streaming: bool) -> None:
        self.streaming = streaming

    async def execute(
        self,
        request: MessagesRequest,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
    ) -> PipelineResult:
        del session_id, agent_id
        context = RequestContext(
            original_model=request.model,
            original_payload=request.model_dump(mode="json"),
            resolved_model="claude-test",
            state=RequestState.STREAMING if self.streaming else RequestState.COMPLETED,
            attempts=[Attempt(number=0, status_code=200)],
        )
        if self.streaming:
            response = httpx2.Response(200, stream=BytesStream())
        else:
            response = httpx2.Response(
                200,
                json={
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-test",
                    "content": [{"type": "text", "text": "hello"}],
                    "future": True,
                },
            )
        return PipelineResult(context=context, response=response)

    async def observe_stream_finalized(
        self,
        request: MessagesRequest,
        context: RequestContext,
        *,
        usage: dict[str, int],
        completed: bool,
        usage_estimated: bool = False,
    ) -> None:
        del request, context, usage, completed, usage_estimated


class StubCounter:
    async def count(self, request: MessagesRequest) -> dict[str, Any]:
        assert request.model == "claude-test"
        return {"input_tokens": 12, "future": True}


class ExecutableAnthropicClient(Protocol):
    async def execute(
        self,
        request: MessagesRequest,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
    ) -> PipelineResult: ...

    async def observe_stream_finalized(
        self,
        request: MessagesRequest,
        context: RequestContext,
        *,
        usage: dict[str, int],
        completed: bool,
        usage_estimated: bool = False,
    ) -> None: ...


class FailingAnthropicClient:
    async def execute(
        self,
        request: MessagesRequest,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
    ) -> PipelineResult:
        del session_id, agent_id
        context = RequestContext(
            original_model=request.model,
            original_payload=request.model_dump(mode="json"),
            state=RequestState.FAILED,
        )
        response = httpx2.Response(
            429,
            request=httpx2.Request("POST", "https://upstream.test/v1/messages"),
            json={"type": "error", "error": {"type": "rate_limit_error"}},
        )
        raise UpstreamResponseError(context, response)

    async def observe_stream_finalized(
        self,
        request: MessagesRequest,
        context: RequestContext,
        *,
        usage: dict[str, int],
        completed: bool,
        usage_estimated: bool = False,
    ) -> None:
        del request, context, usage, completed, usage_estimated


def _app(client: ExecutableAnthropicClient):
    app = create_app(AppSettings())
    app.dependency_overrides[get_anthropic_client] = lambda: client
    app.dependency_overrides[get_token_counter] = lambda: StubCounter()
    return app


def test_post_v1_messages_non_streaming_preserves_response() -> None:
    with TestClient(_app(StubAnthropicClient(streaming=False))) as client:
        response = client.post(
            "/v1/messages",
            json={
                "model": "claude-test",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["future"] is True


def test_post_v1_messages_streaming_passthrough_headers() -> None:
    with TestClient(_app(StubAnthropicClient(streaming=True))) as client:
        response = client.post(
            "/v1/messages",
            json={
                "model": "claude-test",
                "max_tokens": 100,
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert response.content == b'event: message_stop\ndata: {"type":"message_stop"}\n\n'


def test_post_count_tokens_returns_service_result() -> None:
    with TestClient(_app(StubAnthropicClient(streaming=False))) as client:
        response = client.post(
            "/v1/messages/count_tokens",
            json={
                "model": "claude-test",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert response.status_code == 200
    assert response.json() == {"input_tokens": 12, "future": True}


def test_warmup_fake_policy_short_circuits_upstream() -> None:
    settings = AppSettings.model_validate({"anthropic": {"warmup": "fake"}})
    app = create_app(settings)
    app.dependency_overrides[get_anthropic_client] = lambda: StubAnthropicClient(
        streaming=False
    )
    app.dependency_overrides[get_token_counter] = lambda: StubCounter()
    with TestClient(app) as client:
        response = client.post(
            "/v1/messages",
            json={
                "model": "claude-test",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Warmup"}],
            },
        )
    assert response.status_code == 200
    assert response.json()["content"][0]["text"] == "Cache warmed."


def test_upstream_error_status_and_body_are_forwarded() -> None:
    with TestClient(_app(FailingAnthropicClient())) as client:
        response = client.post(
            "/v1/messages",
            json={
                "model": "claude-test",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert response.status_code == 429
    assert response.json() == {
        "type": "error",
        "error": {"type": "rate_limit_error"},
    }
