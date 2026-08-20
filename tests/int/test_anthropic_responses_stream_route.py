from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, cast

import httpx
import orjson
import pytest
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect
from starlette.types import Message, Receive, Scope, Send

from app.anthropic.client import AnthropicClient
from app.config.settings import AppSettings
from app.delivery.responses_anthropic_stream import (
    ResponsesAnthropicStreamState,
    render_responses_as_anthropic_sse,
)
from app.deps import get_anthropic_client, get_settings
from app.hooks.context import HookContext
from app.hooks.executor import HooksExecutor
from app.hooks.registry import HookRegistryBuilder
from app.hooks.types import ObserverEvent
from app.pipeline.approval import ApprovalGate, ApprovalResult
from app.pipeline.context import RequestContext, RequestState
from app.server.app_factory import create_app
from app.streaming.sse import create_delayed_sse_response
from app.transform.model_resolver import ModelResolver
from app.upstream.models_api import ModelCatalog


@dataclass(slots=True)
class _Chunk:
    data: bytes
    consumed: asyncio.Event = field(default_factory=asyncio.Event)


class ControlledResponsesStream(httpx.AsyncByteStream):
    def __init__(self, *, checkpoint_close: bool = False) -> None:
        self._queue = asyncio.Queue[_Chunk | None]()
        self.closed = False
        self.checkpoint_close = checkpoint_close
        self.close_started = asyncio.Event()
        self.allow_close = asyncio.Event()
        self.close_finished = asyncio.Event()

    async def __aiter__(self) -> AsyncIterator[bytes]:
        while (chunk := await self._queue.get()) is not None:
            yield chunk.data
            chunk.consumed.set()

    async def feed(self, data: bytes, *, wait_consumed: bool = True) -> None:
        chunk = _Chunk(data)
        await self._queue.put(chunk)
        if wait_consumed:
            await asyncio.wait_for(chunk.consumed.wait(), timeout=1)

    async def finish(self) -> None:
        await self._queue.put(None)

    async def aclose(self) -> None:
        self.close_started.set()
        if self.checkpoint_close:
            await self.allow_close.wait()
            await asyncio.sleep(0)
        self.closed = True
        await self._queue.put(None)
        self.close_finished.set()


class StaticResponsesStream(httpx.AsyncByteStream):
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self._chunks = chunks
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


@dataclass(slots=True)
class RecordingTarget:
    stream: httpx.AsyncByteStream
    called: asyncio.Event = field(default_factory=asyncio.Event)
    responses_payloads: list[dict[str, Any]] = field(
        default_factory=lambda: list[dict[str, Any]]()
    )

    async def send_anthropic(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        del payload, stream, extra_headers
        raise AssertionError("Responses-only model must not use Messages upstream")

    async def send_responses_headers(
        self,
        payload: Mapping[str, Any],
    ) -> httpx.Response:
        self.responses_payloads.append(dict(payload))
        self.called.set()
        return httpx.Response(
            200,
            headers={
                "content-type": "text/event-stream",
                "content-length": "99999",
                "request-id": "req_stream_responses",
                "x-ratelimit-remaining-requests": "7",
                "x-internal-openai": "must-not-forward",
                "transfer-encoding": "chunked",
            },
            request=httpx.Request("POST", "https://upstream.test/responses"),
            stream=self.stream,
        )


@dataclass(slots=True)
class RecordingHistory:
    started_contexts: list[RequestContext] = field(
        default_factory=lambda: list[RequestContext]()
    )
    finalized_contexts: list[RequestContext] = field(
        default_factory=lambda: list[RequestContext]()
    )
    responses: list[dict[str, Any] | None] = field(
        default_factory=lambda: list[dict[str, Any] | None]()
    )
    usages: list[dict[str, int] | None] = field(
        default_factory=lambda: list[dict[str, int] | None]()
    )
    usage_estimated: list[bool] = field(default_factory=lambda: list[bool]())
    checkpoint_finalize: bool = False
    finalize_started: asyncio.Event = field(default_factory=asyncio.Event)
    allow_finalize: asyncio.Event = field(default_factory=asyncio.Event)
    finalize_finished: asyncio.Event = field(default_factory=asyncio.Event)

    async def started(self, context: RequestContext) -> None:
        self.started_contexts.append(context)

    async def finalized(
        self,
        context: RequestContext,
        *,
        response: dict[str, Any] | None = None,
        usage: Mapping[str, int] | None = None,
        usage_estimated: bool = False,
    ) -> None:
        self.finalize_started.set()
        if self.checkpoint_finalize:
            await self.allow_finalize.wait()
            await asyncio.sleep(0)
        self.finalized_contexts.append(context)
        self.responses.append(response)
        self.usages.append(dict(usage) if usage is not None else None)
        self.usage_estimated.append(usage_estimated)
        self.finalize_finished.set()


@dataclass(slots=True)
class RecordingApproval:
    enabled: bool = True
    contexts: list[RequestContext] = field(default_factory=lambda: list[RequestContext]())

    async def wait_for_approval(self, context: RequestContext) -> ApprovalResult:
        self.contexts.append(context)
        return ApprovalResult("approved")


@dataclass(slots=True)
class RecordingObserver:
    name: str = "responses-stream-route-smoke"
    order: int = 1000
    events: frozenset[ObserverEvent] = frozenset(
        {
            ObserverEvent.REQUEST_RECEIVED,
            ObserverEvent.RESPONSE,
            ObserverEvent.ERROR,
            ObserverEvent.FINALIZE,
        }
    )
    seen: list[tuple[ObserverEvent, HookContext, Mapping[str, Any]]] = field(
        default_factory=lambda: list[
            tuple[ObserverEvent, HookContext, Mapping[str, Any]]
        ]()
    )
    checkpoint_finalize: bool = False
    finalize_started: asyncio.Event = field(default_factory=asyncio.Event)
    allow_finalize: asyncio.Event = field(default_factory=asyncio.Event)
    finalize_finished: asyncio.Event = field(default_factory=asyncio.Event)

    async def observe(
        self,
        event: ObserverEvent,
        context: HookContext,
        data: Mapping[str, Any],
    ) -> None:
        if event is ObserverEvent.FINALIZE:
            self.finalize_started.set()
            if self.checkpoint_finalize:
                await self.allow_finalize.wait()
                await asyncio.sleep(0)
        self.seen.append((event, context, data))
        if event is ObserverEvent.FINALIZE:
            self.finalize_finished.set()


@dataclass(slots=True)
class Harness:
    app: Any
    target: RecordingTarget
    history: RecordingHistory
    approval: RecordingApproval
    observer: RecordingObserver


def _harness(
    stream: httpx.AsyncByteStream,
    *,
    checkpoint_finalize: bool = False,
    route_upstream_type: Literal["copilot", "generic"] = "copilot",
) -> Harness:
    settings = AppSettings.model_validate(
        {
            "anthropic": {"route_override": "responses"},
            "history": {"enabled": False},
        }
    )
    catalog = ModelCatalog(None, "https://upstream.test")
    catalog.replace_from_data(
        {
            "object": "list",
            "data": [
                {
                    "id": "resolved-model",
                    "vendor": "test",
                    "supported_endpoints": ["/responses"],
                }
            ],
        }
    )
    target = RecordingTarget(stream)
    history = RecordingHistory(checkpoint_finalize=checkpoint_finalize)
    approval = RecordingApproval()
    observer = RecordingObserver(checkpoint_finalize=checkpoint_finalize)
    hooks_builder = HookRegistryBuilder()
    hooks_builder.register_observer(observer)
    anthropic = AnthropicClient(
        target,
        ModelResolver(
            available_ids=catalog.available_ids,
            model_overrides={},
            model_mappings={"requested-model": "resolved-model"},
        ),
        settings,
        history=cast(Any, history),
        approval_gate=cast(ApprovalGate, approval),
        hooks=HooksExecutor(hooks_builder.build(), user_timeout_ms=1_000),
        model_catalog=catalog,
    )
    app = create_app(settings)
    app.dependency_overrides[get_anthropic_client] = lambda: anthropic
    if route_upstream_type != settings.upstream.type:
        route_settings = settings.model_copy(
            update={
                "upstream": settings.upstream.model_copy(
                    update={"type": route_upstream_type}
                )
            }
        )
        app.dependency_overrides[get_settings] = lambda: route_settings
    return Harness(app, target, history, approval, observer)


def _request_body() -> dict[str, Any]:
    return {
        "model": "requested-model",
        "max_tokens": 64,
        "stream": True,
        "messages": [{"role": "user", "content": "hello"}],
        "tools": [
            {
                "name": "weather",
                "description": "Get weather",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            }
        ],
    }


def _sse(payload: Mapping[str, Any]) -> bytes:
    return (
        b"event: "
        + cast(str, payload["type"]).encode()
        + b"\n"
        + b"data: "
        + orjson.dumps(payload)
        + b"\n\n"
    )


def _scope(body: bytes, *, spec_version: str = "2.3") -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/messages",
        "raw_path": b"/v1/messages",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"x-claude-code-session-id", b"session-stream-route"),
            (b"x-claude-code-agent-id", b"agent-stream-route"),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "state": {},
    }


async def _wait_for_message(messages: list[Message], message_type: str) -> Message:
    async with asyncio.timeout(1):
        while True:
            for message in messages:
                if message["type"] == message_type:
                    return message
            await asyncio.sleep(0)


def _event_names(body: bytes) -> list[str]:
    return [
        line.removeprefix(b"event: ").decode()
        for line in body.splitlines()
        if line.startswith(b"event: ")
    ]


def _decode_events(body: bytes) -> list[tuple[str, dict[str, Any]]]:
    decoded: list[tuple[str, dict[str, Any]]] = []
    for frame in body.split(b"\n\n"):
        if not frame:
            continue
        event_name: str | None = None
        data: bytes | None = None
        for line in frame.splitlines():
            if line.startswith(b"event: "):
                event_name = line.removeprefix(b"event: ").decode()
            elif line.startswith(b"data: "):
                data = line.removeprefix(b"data: ")
        assert event_name is not None and data is not None
        payload = orjson.loads(data)
        assert isinstance(payload, dict)
        typed = cast(dict[str, Any], payload)
        assert typed["type"] == event_name
        decoded.append((event_name, typed))
    return decoded


_EMPTY_MESSAGE_EVENTS: tuple[dict[str, Any], ...] = (
    {
        "type": "response.output_item.added",
        "output_index": 0,
        "item": {"id": "msg_empty", "type": "message", "content": []},
    },
    {
        "type": "response.output_item.done",
        "output_index": 0,
        "item": {"id": "msg_empty", "type": "message", "content": []},
    },
    {
        "type": "response.completed",
        "response": {
            "id": "resp_semantic_bad",
            "status": "completed",
            "usage": {"input_tokens": 1, "output_tokens": 0},
        },
    },
)

_INVALID_TOOL_ARGUMENT_EVENTS: tuple[dict[str, Any], ...] = (
    {
        "type": "response.output_item.added",
        "output_index": 0,
        "item": {
            "id": "fc_bad",
            "type": "function_call",
            "call_id": "call_bad",
            "name": "weather",
            "arguments": "",
        },
    },
    {
        "type": "response.function_call_arguments.done",
        "output_index": 0,
        "item_id": "fc_bad",
        "arguments": "[]",
    },
)


@pytest.mark.asyncio
async def test_adapter_advances_frontier_only_after_downstream_resumes_yield() -> None:
    source = StaticResponsesStream(
        (
            _sse(
                {
                    "type": "response.created",
                    "response": {
                        "id": "resp_frontier",
                        "model": "resolved-model",
                        "status": "in_progress",
                    },
                }
            ),
            _sse(
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {"id": "msg_frontier", "type": "message", "content": []},
                }
            ),
            _sse(
                {
                    "type": "response.output_item.done",
                    "output_index": 0,
                    "item": {
                        "id": "msg_frontier",
                        "type": "message",
                        "content": [{"type": "output_text", "text": "accepted later"}],
                    },
                }
            ),
            _sse(
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_frontier",
                        "status": "completed",
                        "usage": {"input_tokens": 2, "output_tokens": 2},
                    },
                }
            ),
        )
    )
    state = ResponsesAnthropicStreamState()
    rendered = render_responses_as_anthropic_sse(
        source.__aiter__(),
        model="resolved-model",
        state=state,
    )

    first = await anext(rendered)
    assert b"accepted later" in first
    assert state.frontier is not None
    assert state.frontier.headers_state == "not_started"
    assert state.frontier.committed_blocks == ()

    terminal = await anext(rendered)
    assert b"message_stop" in terminal
    assert state.frontier.headers_state == "accepted"
    assert len(state.frontier.committed_blocks) == 1
    assert state.frontier.terminal_state == "not_started"

    with pytest.raises(StopAsyncIteration):
        await anext(rendered)
    assert state.frontier.terminal_accepted is True


@pytest.mark.asyncio
async def test_first_body_send_failure_marks_envelopes_uncertain_without_commit() -> None:
    source = StaticResponsesStream(
        (
            _sse(
                {
                    "type": "response.created",
                    "response": {
                        "id": "resp_sink_failure",
                        "model": "resolved-model",
                        "status": "in_progress",
                    },
                }
            ),
            _sse(
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {"id": "msg_sink_failure", "type": "message", "content": []},
                }
            ),
            _sse(
                {
                    "type": "response.output_item.done",
                    "output_index": 0,
                    "item": {
                        "id": "msg_sink_failure",
                        "type": "message",
                        "content": [{"type": "output_text", "text": "uncertain"}],
                    },
                }
            ),
        )
    )
    state = ResponsesAnthropicStreamState()
    rendered = render_responses_as_anthropic_sse(
        source.__aiter__(),
        model="resolved-model",
        state=state,
    )
    response = create_delayed_sse_response(
        rendered,
        on_start_accepted=state.accept_headers,
        on_start_uncertain=state.mark_headers_uncertain,
        on_body_uncertain=state.mark_body_uncertain,
    )
    sends = 0

    async def send(message: Message) -> None:
        nonlocal sends
        sends += 1
        if message["type"] == "http.response.body":
            raise OSError("body outcome unknown")

    with pytest.raises(OSError, match="outcome unknown"):
        await response.stream_response(cast(Send, send))

    assert sends == 2
    assert state.frontier is not None
    assert state.frontier.headers_state == "accepted"
    assert state.frontier.message_start_state == "uncertain"
    assert state.frontier.block_state(0) == "uncertain"
    assert state.frontier.committed_blocks == ()
    assert state.committed_response == {
        "id": state.message_id,
        "type": "message",
        "role": "assistant",
        "content": [],
        "model": "resolved-model",
        "stop_reason": None,
        "stop_sequence": None,
        "delivery": {
            "complete": False,
            "uncertain": True,
            "headers_state": "accepted",
            "message_start_state": "uncertain",
            "terminal_state": "not_started",
            "uncertain_block_index": 0,
            "possibly_visible_block": {"type": "text", "text": "uncertain"},
        },
    }


@pytest.mark.asyncio
async def test_first_body_uncertainty_is_projected_into_history() -> None:
    stream = StaticResponsesStream(
        (
            _sse(
                {
                    "type": "response.created",
                    "response": {
                        "id": "resp_history_uncertain",
                        "model": "resolved-model",
                        "status": "in_progress",
                    },
                }
            ),
            _sse(
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {"id": "msg_uncertain", "type": "message", "content": []},
                }
            ),
            _sse(
                {
                    "type": "response.output_item.done",
                    "output_index": 0,
                    "item": {
                        "id": "msg_uncertain",
                        "type": "message",
                        "content": [{"type": "output_text", "text": "maybe visible"}],
                    },
                }
            ),
        )
    )
    harness = _harness(stream)
    request_body = orjson.dumps(_request_body())
    request_sent = False

    async def receive() -> Message:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": request_body, "more_body": False}
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            raise OSError("body outcome unknown")

    with pytest.raises(ClientDisconnect):
        await harness.app(
            _scope(request_body),
            cast(Receive, receive),
            cast(Send, send),
        )

    assert stream.closed is True
    assert len(harness.history.responses) == 1
    history_response = harness.history.responses[0]
    assert history_response is not None
    assert history_response["content"] == []
    assert history_response["delivery"] == {
        "complete": False,
        "uncertain": True,
        "headers_state": "accepted",
        "message_start_state": "uncertain",
        "terminal_state": "not_started",
        "uncertain_block_index": 0,
        "possibly_visible_block": {"type": "text", "text": "maybe visible"},
    }
    assert history_response["error"]["code"] == "delivery_uncertain"
    context = harness.history.finalized_contexts[0]
    assert context.state is RequestState.FAILED
    assert context.error is not None
    assert context.error.code == "delivery_uncertain"


@pytest.mark.asyncio
async def test_chunked_responses_sse_reaches_real_anthropic_asgi_after_complete_block() -> None:
    upstream = ControlledResponsesStream()
    harness = _harness(upstream)
    request_body = orjson.dumps(_request_body())
    request_sent = False
    disconnect = asyncio.Event()
    sent: list[Message] = []

    async def receive() -> Message:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": request_body, "more_body": False}
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    app_task = asyncio.create_task(
        harness.app(_scope(request_body), cast(Receive, receive), cast(Send, send))
    )
    await asyncio.wait_for(harness.target.called.wait(), timeout=1)

    created = _sse(
        {
            "type": "response.created",
            "response": {
                "id": "resp_stream_vertical",
                "model": "resolved-model",
                "status": "in_progress",
            },
        }
    )
    await upstream.feed(created[:17])
    await upstream.feed(created[17:])
    await upstream.feed(
        _sse(
            {
                "type": "response.in_progress",
                "response": {
                    "id": "resp_stream_vertical",
                    "model": "resolved-model",
                    "status": "in_progress",
                },
            }
        )
    )
    await upstream.feed(
        _sse(
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {
                    "id": "rs_0",
                    "type": "reasoning",
                    "summary": [],
                    "encrypted_content": None,
                },
            }
        )
    )
    await upstream.feed(
        _sse(
            {
                "type": "response.reasoning_summary_text.delta",
                "output_index": 0,
                "item_id": "rs_0",
                "summary_index": 0,
                "delta": "checked",
            }
        )
    )
    await upstream.feed(
        _sse(
            {
                "type": "response.reasoning_summary_text.done",
                "output_index": 0,
                "item_id": "rs_0",
                "summary_index": 0,
                "text": "checked",
            }
        )
    )
    assert sent == []

    await upstream.feed(
        _sse(
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "item": {
                    "id": "rs_0",
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "checked"}],
                    "encrypted_content": "opaque-state",
                },
            }
        ),
        wait_consumed=False,
    )
    start = await _wait_for_message(sent, "http.response.start")
    first_body = await _wait_for_message(sent, "http.response.body")

    assert start["status"] == 200
    headers = {name.decode().lower(): value.decode() for name, value in start["headers"]}
    assert headers["request-id"] == "req_stream_responses"
    assert headers["x-ratelimit-remaining-requests"] == "7"
    assert "x-internal-openai" not in headers
    assert headers["content-type"].startswith("text/event-stream")
    assert headers.get("content-length") != "99999"
    assert _event_names(first_body["body"]) == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_delta",
        "content_block_stop",
    ]

    remaining_events: tuple[dict[str, Any], ...] = (
        {
            "type": "response.output_item.added",
            "output_index": 1,
            "item": {"id": "msg_1", "type": "message", "content": []},
        },
        {
            "type": "response.content_part.added",
            "output_index": 1,
            "item_id": "msg_1",
            "content_index": 0,
            "part": {"type": "output_text", "text": ""},
        },
        {
            "type": "response.output_text.delta",
            "output_index": 1,
            "item_id": "msg_1",
            "content_index": 0,
            "delta": "hello bridge",
        },
        {
            "type": "response.output_text.done",
            "output_index": 1,
            "item_id": "msg_1",
            "content_index": 0,
            "text": "hello bridge",
        },
        {
            "type": "response.content_part.done",
            "output_index": 1,
            "item_id": "msg_1",
            "content_index": 0,
            "part": {"type": "output_text", "text": "hello bridge"},
        },
        {
            "type": "response.output_item.done",
            "output_index": 1,
            "item": {
                "id": "msg_1",
                "type": "message",
                "content": [{"type": "output_text", "text": "hello bridge"}],
            },
        },
        {
            "type": "response.output_item.added",
            "output_index": 2,
            "item": {
                "id": "fc_2",
                "type": "function_call",
                "call_id": "call_weather",
                "name": "weather",
                "arguments": "",
            },
        },
        {
            "type": "response.function_call_arguments.delta",
            "output_index": 2,
            "item_id": "fc_2",
            "delta": '{"city":"Paris"}',
        },
        {
            "type": "response.function_call_arguments.done",
            "output_index": 2,
            "item_id": "fc_2",
            "arguments": '{"city":"Paris"}',
        },
        {
            "type": "response.output_item.done",
            "output_index": 2,
            "item": {
                "id": "fc_2",
                "type": "function_call",
                "call_id": "call_weather",
                "name": "weather",
                "arguments": '{"city":"Paris"}',
            },
        },
    )
    for event in remaining_events:
        await upstream.feed(
            _sse(event),
            wait_consumed=event["type"] != "response.output_item.done",
        )
    await upstream.feed(
        _sse(
            {
                "type": "response.completed",
                "response": {
                    "id": "resp_stream_vertical",
                    "model": "resolved-model",
                    "status": "completed",
                    "usage": {
                        "input_tokens": 12,
                        "output_tokens": 7,
                        "total_tokens": 19,
                    },
                },
            }
        ),
        wait_consumed=False,
    )
    await upstream.finish()

    await asyncio.wait_for(app_task, timeout=1)
    body = b"".join(
        cast(bytes, message.get("body", b""))
        for message in sent
        if message["type"] == "http.response.body"
    )
    assert _event_names(body) == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_delta",
        "content_block_stop",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]
    assert b"hello bridge" in body
    assert b'"partial_json":"{\\"city\\":\\"Paris\\"}"' in body
    assert b'"stop_reason":"tool_use"' in body
    assert harness.target.responses_payloads[0]["stream"] is True
    assert harness.target.responses_payloads[0]["model"] == "resolved-model"

    assert len(harness.history.started_contexts) == 1
    assert harness.history.finalized_contexts == harness.history.started_contexts
    context = harness.history.finalized_contexts[0]
    assert harness.approval.contexts == [context]
    assert context.state is RequestState.COMPLETED
    assert context.protocol_leg == "responses"
    assert context.session_id == "session-stream-route"
    assert context.agent_id == "agent-stream-route"
    assert len(context.attempts) == 1
    assert [event for event, _, _ in harness.observer.seen] == [
        ObserverEvent.REQUEST_RECEIVED,
        ObserverEvent.RESPONSE,
        ObserverEvent.FINALIZE,
    ]
    assert {hook_context.request_id for _, hook_context, _ in harness.observer.seen} == {
        context.id
    }
    assert upstream.closed is True
    assert harness.history.responses == [
        {
            "id": next(
                payload["message"]["id"]
                for message in sent
                if message["type"] == "http.response.body"
                for name, payload in _decode_events(cast(bytes, message.get("body", b"")))
                if name == "message_start"
            ),
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "thinking",
                    "thinking": "checked",
                    "signature": (
                        "ghc-api-proxy:synthetic-reasoning:v1:"
                        "eyJ0YWciOiJvcGVuYWkucmVzcG9uc2VzLnJlYXNvbmluZy5lbmNyeXB0ZWRf"
                        "Y29udGVudCIsImVuY3J5cHRlZF9jb250ZW50Ijoib3BhcXVlLXN0YXRlIn0"
                    ),
                },
                {"type": "text", "text": "hello bridge"},
                {
                    "type": "tool_use",
                    "id": "call_weather",
                    "name": "weather",
                    "input": {"city": "Paris"},
                },
            ],
            "model": "resolved-model",
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "delivery": {"complete": True, "uncertain": False},
            "usage": {
                "input_tokens": 12,
                "output_tokens": 7,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        }
    ]


@pytest.mark.parametrize(
    "event",
    [
        pytest.param(
            {"type": "response.future.delta", "output_index": 0},
            id="unknown-event",
        )
    ],
)
def test_precommit_unsupported_responses_event_is_a_typed_failure(
    event: dict[str, Any],
) -> None:
    stream = StaticResponsesStream(
        (
            _sse(
                {
                    "type": "response.created",
                    "response": {
                        "id": "resp_bad",
                        "model": "resolved-model",
                        "status": "in_progress",
                    },
                }
            ),
            _sse(event),
        )
    )
    harness = _harness(stream)

    with TestClient(harness.app) as client:
        response = client.post("/v1/messages", json=_request_body())

    assert response.status_code == 502
    assert response.json() == {
        "type": "error",
        "error": {
            "type": "upstream_error",
            "message": "unsupported Responses event: response.future.delta",
            "code": "unsupported_responses_event",
        },
    }
    assert harness.history.finalized_contexts == harness.history.started_contexts
    context = harness.history.finalized_contexts[0]
    assert context.state is RequestState.FAILED
    assert context.error is not None
    assert context.error.code == "unsupported_responses_event"
    assert [event for event, _, _ in harness.observer.seen] == [
        ObserverEvent.REQUEST_RECEIVED,
        ObserverEvent.ERROR,
        ObserverEvent.FINALIZE,
    ]
    assert stream.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
async def test_disconnect_while_prefetching_closes_upstream_without_success_headers(
    spec_version: str,
) -> None:
    upstream = ControlledResponsesStream()
    harness = _harness(upstream)
    request_body = orjson.dumps(_request_body())
    request_sent = False
    disconnect = asyncio.Event()
    sent: list[Message] = []

    async def receive() -> Message:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": request_body, "more_body": False}
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    app_task = asyncio.create_task(
        harness.app(
            _scope(request_body, spec_version=spec_version),
            cast(Receive, receive),
            cast(Send, send),
        )
    )
    await asyncio.wait_for(harness.target.called.wait(), timeout=1)

    disconnect.set()
    await asyncio.wait_for(app_task, timeout=1)

    assert sent == []
    assert upstream.closed is True
    assert harness.history.finalized_contexts == harness.history.started_contexts
    context = harness.history.finalized_contexts[0]
    assert context.state is RequestState.FAILED
    assert context.error is not None
    assert context.error.status_code == 499
    assert len(context.attempts) == 1
    assert [event for event, _, _ in harness.observer.seen] == [
        ObserverEvent.REQUEST_RECEIVED,
        ObserverEvent.ERROR,
        ObserverEvent.FINALIZE,
    ]


@pytest.mark.asyncio
async def test_prefetch_disconnect_waits_for_checkpoint_cleanup_after_recancellation() -> None:
    upstream = ControlledResponsesStream(checkpoint_close=True)
    harness = _harness(upstream, checkpoint_finalize=True)
    request_body = orjson.dumps(_request_body())
    request_sent = False
    disconnect = asyncio.Event()

    async def receive() -> Message:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": request_body, "more_body": False}
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        raise AssertionError(f"disconnect before prefetch must not send {message['type']}")

    app_task = asyncio.create_task(
        harness.app(_scope(request_body), cast(Receive, receive), cast(Send, send))
    )
    await asyncio.wait_for(harness.target.called.wait(), timeout=1)

    disconnect.set()
    await asyncio.wait_for(harness.observer.finalize_started.wait(), timeout=1)
    app_task.cancel()
    harness.observer.allow_finalize.set()
    await asyncio.wait_for(harness.history.finalize_started.wait(), timeout=1)
    harness.history.allow_finalize.set()
    await asyncio.wait_for(upstream.close_started.wait(), timeout=1)
    upstream.allow_close.set()

    with pytest.raises(asyncio.CancelledError):
        await app_task

    assert harness.observer.finalize_finished.is_set()
    assert harness.history.finalize_finished.is_set()
    assert upstream.close_finished.is_set()
    assert len(harness.history.finalized_contexts) == 1
    assert [event for event, _, _ in harness.observer.seen].count(
        ObserverEvent.FINALIZE
    ) == 1


def test_postcommit_protocol_failure_emits_error_sse_and_saves_partial_history() -> None:
    stream = StaticResponsesStream(
        (
            _sse(
                {
                    "type": "response.created",
                    "response": {
                        "id": "resp_partial",
                        "model": "resolved-model",
                        "status": "in_progress",
                    },
                }
            ),
            _sse(
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {"id": "msg_partial", "type": "message", "content": []},
                }
            ),
            _sse(
                {
                    "type": "response.output_text.done",
                    "output_index": 0,
                    "item_id": "msg_partial",
                    "content_index": 0,
                    "text": "committed prefix",
                }
            ),
            _sse(
                {
                    "type": "response.output_item.done",
                    "output_index": 0,
                    "item": {
                        "id": "msg_partial",
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "committed prefix"}
                        ],
                    },
                }
            ),
            _sse({"type": "response.future.delta", "output_index": 1}),
        )
    )
    harness = _harness(stream)

    with TestClient(harness.app) as client:
        response = client.post("/v1/messages", json=_request_body())

    assert response.status_code == 200
    assert _event_names(response.content) == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "error",
    ]
    assert b"message_stop" not in response.content
    assert b"unsupported_responses_event" in response.content
    context = harness.history.finalized_contexts[0]
    assert context.state is RequestState.FAILED
    assert harness.history.responses == [
        {
            "id": cast(dict[str, Any], _decode_events(response.content)[0][1]["message"])[
                "id"
            ],
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "committed prefix"}],
            "model": "resolved-model",
            "stop_reason": None,
            "stop_sequence": None,
            "delivery": {"complete": False, "uncertain": False},
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "error": {
                "type": "upstream_error",
                "message": "unsupported Responses event: response.future.delta",
                "code": "unsupported_responses_event",
            },
        }
    ]
    assert stream.closed is True


def test_max_output_tokens_incomplete_is_successful_max_tokens_terminal() -> None:
    stream = StaticResponsesStream(
        (
            _sse(
                {
                    "type": "response.created",
                    "response": {
                        "id": "resp_limited",
                        "model": "resolved-model",
                        "status": "in_progress",
                    },
                }
            ),
            _sse(
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {"id": "msg_limited", "type": "message", "content": []},
                }
            ),
            _sse(
                {
                    "type": "response.output_item.done",
                    "output_index": 0,
                    "item": {
                        "id": "msg_limited",
                        "type": "message",
                        "content": [{"type": "output_text", "text": "limited"}],
                    },
                }
            ),
            _sse(
                {
                    "type": "response.incomplete",
                    "response": {
                        "id": "resp_limited",
                        "status": "incomplete",
                        "incomplete_details": {"reason": "max_output_tokens"},
                        "usage": {"input_tokens": 4, "output_tokens": 64},
                    },
                }
            ),
        )
    )
    harness = _harness(stream)

    with TestClient(harness.app) as client:
        response = client.post("/v1/messages", json=_request_body())

    assert response.status_code == 200
    assert b'"stop_reason":"max_tokens"' in response.content
    assert _event_names(response.content)[-2:] == ["message_delta", "message_stop"]
    assert harness.history.finalized_contexts[0].state is RequestState.COMPLETED
    assert harness.history.responses[0] is not None
    assert harness.history.responses[0]["delivery"]["complete"] is True


def test_max_output_tokens_without_usage_uses_estimated_zero_usage() -> None:
    stream = StaticResponsesStream(
        (
            _sse(
                {
                    "type": "response.created",
                    "response": {
                        "id": "resp_limited_no_usage",
                        "model": "resolved-model",
                        "status": "in_progress",
                    },
                }
            ),
            _sse(
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {"id": "msg_limited", "type": "message", "content": []},
                }
            ),
            _sse(
                {
                    "type": "response.output_item.done",
                    "output_index": 0,
                    "item": {
                        "id": "msg_limited",
                        "type": "message",
                        "content": [{"type": "output_text", "text": "limited"}],
                    },
                }
            ),
            _sse(
                {
                    "type": "response.incomplete",
                    "response": {
                        "id": "resp_limited_no_usage",
                        "status": "incomplete",
                        "incomplete_details": {"reason": "max_output_tokens"},
                    },
                }
            ),
        )
    )
    harness = _harness(stream)

    with TestClient(harness.app) as client:
        response = client.post("/v1/messages", json=_request_body())

    assert response.status_code == 200
    events = _decode_events(response.content)
    assert events[-2][0] == "message_delta"
    assert events[-2][1]["usage"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    assert events[-1][0] == "message_stop"
    history_response = harness.history.responses[0]
    assert history_response is not None
    assert history_response["usage"] == events[-2][1]["usage"]
    assert history_response["usage_facts"] == {"estimated": True}
    response_observation = next(
        data
        for event, _, data in harness.observer.seen
        if event is ObserverEvent.RESPONSE
    )
    assert response_observation["usage"] == events[-2][1]["usage"]
    assert response_observation["usage_facts"] == {"estimated": True}


def test_copilot_route_accepts_distinct_response_and_item_ids_across_lifecycle() -> None:
    events: tuple[dict[str, Any], ...] = (
        {
            "type": "response.created",
            "response": {
                "id": "resp_copilot_created",
                "model": "resolved-model",
                "status": "in_progress",
            },
        },
        {
            "type": "response.in_progress",
            "response": {
                "id": "resp_copilot_in_progress",
                "model": "resolved-model",
                "status": "in_progress",
            },
        },
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"id": "msg_added", "type": "message", "content": []},
        },
        {
            "type": "response.content_part.added",
            "output_index": 0,
            "item_id": "msg_part_added",
            "content_index": 0,
            "part": {"type": "output_text", "text": ""},
        },
        {
            "type": "response.output_text.delta",
            "output_index": 0,
            "item_id": "msg_delta",
            "content_index": 0,
            "delta": "copilot lifecycle",
        },
        {
            "type": "response.output_text.done",
            "output_index": 0,
            "item_id": "msg_text_done",
            "content_index": 0,
            "text": "copilot lifecycle",
        },
        {
            "type": "response.content_part.done",
            "output_index": 0,
            "item_id": "msg_part_done",
            "content_index": 0,
            "part": {"type": "output_text", "text": "copilot lifecycle"},
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "id": "msg_item_done",
                "type": "message",
                "content": [{"type": "output_text", "text": "copilot lifecycle"}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp_copilot_completed",
                "status": "completed",
                "usage": {"input_tokens": 1, "output_tokens": 2},
            },
        },
    )
    stream = StaticResponsesStream(tuple(_sse(event) for event in events))
    harness = _harness(stream)

    with TestClient(harness.app) as client:
        response = client.post("/v1/messages", json=_request_body())

    assert response.status_code == 200
    assert _event_names(response.content)[-1] == "message_stop"
    assert b"copilot lifecycle" in response.content
    assert b"response_id_mismatch" not in response.content
    assert b"item_id_mismatch" not in response.content
    assert harness.history.finalized_contexts[0].state is RequestState.COMPLETED


def test_generic_route_rejects_distinct_item_ids_across_message_lifecycle() -> None:
    events: tuple[dict[str, Any], ...] = (
        {
            "type": "response.created",
            "response": {
                "id": "resp_generic_item_identity",
                "model": "resolved-model",
                "status": "in_progress",
            },
        },
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"id": "msg_added", "type": "message", "content": []},
        },
        {
            "type": "response.content_part.added",
            "output_index": 0,
            "item_id": "msg_part_added",
            "content_index": 0,
            "part": {"type": "output_text", "text": ""},
        },
    )
    stream = StaticResponsesStream(tuple(_sse(event) for event in events))
    harness = _harness(stream, route_upstream_type="generic")

    with TestClient(harness.app) as client:
        response = client.post("/v1/messages", json=_request_body())

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "item_id_mismatch"
    assert harness.history.finalized_contexts[0].state is RequestState.FAILED


@pytest.mark.parametrize(
    ("terminal_id", "trailing_event", "expected_code"),
    [
        ("resp_other", None, "response_id_mismatch"),
        (
            "resp_identity",
            {"type": "response.future.delta", "output_index": 1},
            "event_after_terminal",
        ),
    ],
)
def test_success_terminal_is_validated_before_message_stop(
    terminal_id: str,
    trailing_event: dict[str, Any] | None,
    expected_code: str,
) -> None:
    events: list[dict[str, Any]] = [
        {
            "type": "response.created",
            "response": {
                "id": "resp_identity",
                "model": "resolved-model",
                "status": "in_progress",
            },
        },
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"id": "msg_identity", "type": "message", "content": []},
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "id": "msg_identity",
                "type": "message",
                "content": [{"type": "output_text", "text": "prefix"}],
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": terminal_id,
                "status": "completed",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        },
    ]
    if trailing_event is not None:
        events.append(trailing_event)
    stream = StaticResponsesStream(tuple(_sse(event) for event in events))
    harness = _harness(stream, route_upstream_type="generic")

    with TestClient(harness.app) as client:
        response = client.post("/v1/messages", json=_request_body())

    assert response.status_code == 200
    assert b"message_stop" not in response.content
    assert expected_code.encode() in response.content
    assert _event_names(response.content)[-1] == "error"
    assert harness.history.finalized_contexts[0].state is RequestState.FAILED


@pytest.mark.parametrize(
    ("events", "expected_code"),
    [
        (_EMPTY_MESSAGE_EVENTS, "empty_response_content"),
        (_INVALID_TOOL_ARGUMENT_EVENTS, "invalid_tool_arguments"),
    ],
)
def test_precommit_semantic_failures_are_typed_anthropic_http_errors(
    events: tuple[dict[str, Any], ...], expected_code: str
) -> None:
    created = {
        "type": "response.created",
        "response": {
            "id": "resp_semantic_bad",
            "model": "resolved-model",
            "status": "in_progress",
        },
    }
    stream = StaticResponsesStream(tuple(_sse(event) for event in (created, *events)))
    harness = _harness(stream)

    with TestClient(harness.app) as client:
        response = client.post("/v1/messages", json=_request_body())

    assert response.status_code == 502
    assert response.json()["error"]["code"] == expected_code
    assert harness.history.finalized_contexts[0].state is RequestState.FAILED
    assert stream.closed is True
