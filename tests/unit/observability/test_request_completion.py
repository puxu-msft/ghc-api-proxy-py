import asyncio
import json
import time
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any, cast

import pytest
from starlette.background import BackgroundTask
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse, Response
from starlette.types import Message, Receive, Scope, Send

import app.observability.request_completion as completion_module
from app.errors import ErrorCategory, ErrorInfo
from app.observability.active_requests import ActiveRequestRegistry
from app.observability.request_completion import (
    DeliveryState,
    FailureCategory,
    FailureOrigin,
    RequestCompletionCoordinator,
)
from app.observability.request_log import format_completion_line
from app.observability.request_trace import RequestTrace
from app.pipeline.delivery.assembling import (
    FailureOrigin as StreamFailureOrigin,
)
from app.pipeline.delivery.assembling import StreamFailure, Terminal
from app.pipeline.delivery.formats.openai_responses_passthrough import (
    responses_passthrough_assembler,
)
from app.pipeline.delivery.sse_source import SseEvent
from app.pipeline.delivery.stream import one_shot_delivery
from app.pipeline.exceptions import UpstreamError
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.response_observation import ResponseAvailability, ResponsesObserver
from app.server.routes.inference import (
    _AccountedResponse,  # pyright: ignore[reportPrivateUsage]
    _AccountedStreamingResponse,  # pyright: ignore[reportPrivateUsage]
    _StreamAccounting,  # pyright: ignore[reportPrivateUsage]
    _tracked_delivery,  # pyright: ignore[reportPrivateUsage]
    _upstream_error_body,  # pyright: ignore[reportPrivateUsage]
)


class RecordingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[object, object]] = []

    def info(self, event: object, *, status: object) -> None:
        self.events.append((event, status))


class ExplodingStore(ActiveRequestRegistry):
    def complete(self, request_id: str, record: Any) -> None:
        raise RuntimeError("store broke")


class ExplodingReporter:
    def warning(self, _message: str, *_args: object) -> None:
        raise RuntimeError("logging handler failed")


def _coordinator(
    monkeypatch: pytest.MonkeyPatch,
    *,
    registry: ActiveRequestRegistry | None = None,
) -> tuple[RequestCompletionCoordinator, RequestTrace, ActiveRequestRegistry, list[dict[str, Any]], RecordingLogger]:
    store = registry or ActiveRequestRegistry()
    trace = RequestTrace(
        method="POST",
        path="/responses",
        request_id="req_1",
        started=time.monotonic(),
        started_at="2026-09-03T00:00:00.000Z",
        inbound_format="openai-responses",
        model="gpt-model",
    )
    trace.upstream_request_body_bytes = 11
    trace.received = 13
    trace.received_known = True
    observer = ResponsesObserver()
    observer.observe_response({
        "status": "completed",
        "model": "gpt-model-2026-01-01",
        "output": [{"type": "function_call", "name": "Bash"}],
        "usage": {
            "input_tokens": 7,
            "input_tokens_details": {"cached_tokens": 2, "cache_write_tokens": 0},
            "output_tokens": 3,
            "output_tokens_details": {"reasoning_tokens": 1},
            "total_tokens": 10,
        },
        "copilot_usage": {"total_nano_aiu": 42},
    })
    trace.absorb_response(observer.snapshot())
    store.add(trace.request_id)
    records: list[dict[str, Any]] = []
    logger = RecordingLogger()

    def keep_record(record: dict[str, Any]) -> None:
        records.append(record)

    def logger_for(_name: str) -> RecordingLogger:
        return logger

    monkeypatch.setattr(completion_module, "write_finalized_record", keep_record)
    monkeypatch.setattr(completion_module, "get_logger", logger_for)
    chain = cast(
        Any,
        SimpleNamespace(
            active_requests=store,
            capabilities=SimpleNamespace(unicode=True, color=False),
        ),
    )
    return (
        RequestCompletionCoordinator(chain, trace, trace.request_id),
        trace,
        store,
        records,
        logger,
    )


def test_finalized_request_is_one_immutable_source_for_store_json_and_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, trace, store, records, logger = _coordinator(monkeypatch)
    completion.mark_response_ready(200)
    completion.note_asgi_message_sent({"type": "http.response.start", "status": 200})
    completion.note_asgi_message_sent({"type": "http.response.body", "body": b"reply"})
    completion.settle(status_code=200, upstream_response_bytes=13)

    first = completion.publish()
    second = completion.publish()

    assert first is second
    snapshot = store.observation_snapshot()
    assert snapshot.live == ()
    assert snapshot.completed == (first,)
    assert len(records) == 1
    assert len(logger.events) == 1
    assert logger.events[0][1] == "ok"

    record = records[0]
    assert record["schema_version"] == 2
    assert set(record) == {
        "at",
        "status",
        "method",
        "path",
        "request_id",
        "message_id",
        "inbound_format",
        "count_tokens",
        "client_protocol",
        "upstream_protocol",
        "requested_model",
        "model",
        "status_code",
        "started_at",
        "duration_s",
        "first_upstream_byte_s",
        "upstream_max_gap_s",
        "upstream_chunks",
        "bytes_in",
        "bytes_out",
        "usage",
        "terminal_seen",
        "stop_reason",
        "blocks",
        "tools",
        "thinking",
        "count_provider",
        "count_provider_reason",
        "dialect",
        "attempts",
        "replaced_failures",
        "tore_after_terminal",
        "detail",
        "upstream_conn",
        "losses",
        "schema_version",
        "observation",
    }
    assert record["status"] == "ok"
    assert record["bytes_in"] == 11
    assert record["bytes_out"] == 13
    observation = cast(dict[str, Any], record["observation"])
    assert set(observation) == {"response", "delivery", "timings", "body_bytes"}
    response = cast(dict[str, Any], observation["response"])
    assert set(response) == {
        "availability",
        "source_protocol",
        "terminal_event_type",
        "terminal_seen",
        "status",
        "incomplete_reason",
        "error",
        "error_summary",
        "model",
        "service_tier",
        "output_items",
        "usage",
        "provider_usage",
        "tool_usage",
        "issues",
    }
    assert response["status"] == "completed"
    assert cast(dict[str, Any], response["provider_usage"])["value"] == {
        "total_nano_aiu": 42
    }
    output_items = cast(list[dict[str, Any]], response["output_items"])
    assert len(output_items) == 1
    assert set(output_items[0]) == {
        "output_index",
        "type",
        "name",
        "status",
        "execution",
        "call_id",
        "reasoning",
        "client_action",
    }
    usage = cast(dict[str, Any], response["usage"])
    assert set(usage) == {"normalized", "raw", "exact", "issues"}
    exact = cast(dict[str, Any], usage["exact"])
    assert set(exact) == {
        "upstream_input_tokens",
        "input_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "computed_total_tokens",
        "upstream_total_tokens",
        "input_tokens_details",
        "output_tokens_details",
        "inconsistent",
    }
    delivery = cast(dict[str, Any], observation["delivery"])
    assert delivery == {
        "state": "accepted",
        "unit": "body",
        "intended_http_status": 200,
        "http_start_accepted": True,
        "downstream_body_bytes": 5,
        "failure": None,
        "post_delivery_failure": None,
        "additional_failures": [],
    }
    body_bytes = cast(dict[str, Any], observation["body_bytes"])
    assert body_bytes == {
        "upstream_request": 11,
        "upstream_response": 13,
        "downstream_response": 5,
    }
    json.dumps(record)

    # Every conversion returns a new mutable DTO. Mutating one sink's copy cannot alter the frozen record or what a later sink reads.
    response["status"] = "mutated"
    fresh = first.to_record_dict()
    fresh_response = cast(
        dict[str, Any],
        cast(dict[str, Any], fresh["observation"])["response"],
    )
    assert fresh_response["status"] == "completed"
    line = first.request_line()
    assert line.tools == ("Bash",)
    rendered = format_completion_line(line, status=first.status)
    assert "↓13B" in rendered
    assert "↓5B" not in rendered, "the completion line used ASGI downstream bytes instead of upstream response-body bytes"
    assert trace.response_observation is first.response


def test_error_only_response_serializes_an_absent_usage_dto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, trace, _store, records, _logger = _coordinator(monkeypatch)
    observer = ResponsesObserver()
    observer.observe_event(
        SseEvent(
            event="error",
            data='{"type":"error","error":{"code":"broken","message":"boom"}}',
        )
    )
    trace.absorb_response(observer.snapshot())
    completion.settle(status_code=200, upstream_response_bytes=1)

    completion.publish()

    response = cast(dict[str, Any], cast(dict[str, Any], records[0]["observation"])["response"])
    usage = cast(dict[str, Any], response["usage"])
    assert cast(dict[str, Any], usage["raw"])["availability"] == "absent"
    assert usage["exact"] is None


def test_one_sink_failure_does_not_block_later_sinks_or_escape(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    completion, _trace, store, records, logger = _coordinator(
        monkeypatch,
        registry=ExplodingStore(),
    )
    completion.mark_response_ready(200)
    completion.note_asgi_message_sent({"type": "http.response.start", "status": 200})
    completion.note_asgi_message_sent({"type": "http.response.body", "body": b"ok"})
    completion.settle(status_code=200, upstream_response_bytes=13)

    record = completion.publish()

    assert record.status == "ok"
    assert len(store.snapshot()) == 1
    assert len(records) == 1
    assert len(logger.events) == 1
    assert "could not emit request store" in caplog.text


def test_sink_and_failure_reporter_can_both_fail_without_escaping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, _trace, store, records, logger = _coordinator(
        monkeypatch,
        registry=ExplodingStore(),
    )
    monkeypatch.setattr(completion_module, "logger", ExplodingReporter())
    completion.mark_response_ready(200)
    completion.note_asgi_message_sent({"type": "http.response.start", "status": 200})
    completion.note_asgi_message_sent({"type": "http.response.body", "body": b"ok"})
    completion.settle(status_code=200, upstream_response_bytes=13)

    record = completion.publish()

    assert record.status == "ok"
    assert len(store.snapshot()) == 1
    assert len(records) == 1
    assert len(logger.events) == 1


HTTP_SCOPE = cast(
    Scope,
    {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "server": ("test", 80),
        "client": ("test", 1),
        "state": {},
    },
)
STREAM_SCOPE = cast(
    Scope,
    {
        **HTTP_SCOPE,
        "asgi": {"version": "3.0", "spec_version": "2.4"},
    },
)


async def receive_request() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


class PathsendResponse(Response):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": self.status_code, "headers": self.raw_headers})
        await send({"type": "http.response.pathsend", "path": "/tmp/file"})
        if self.background is not None:
            await self.background()


class MissingTerminalResponse(Response):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": self.status_code, "headers": self.raw_headers})


class BrokenResponse(Response):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        raise OSError("local response failed")


class AcceptedThenBrokenResponse(Response):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": self.status_code, "headers": self.raw_headers})
        await send({"type": "http.response.body", "body": b"accepted"})
        raise RuntimeError("wrapped response failed after acceptance")


class CancelledResponse(Response):
    def __init__(self, *, after_start: bool) -> None:
        super().__init__()
        self._after_start = after_start

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._after_start:
            await send({"type": "http.response.start", "status": self.status_code, "headers": self.raw_headers})
        raise asyncio.CancelledError("wrapped response cancelled")


class DynamicStartResponse(Response):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 418, "headers": self.raw_headers})
        await send({"type": "http.response.body", "body": b"dynamic"})


@pytest.mark.asyncio
async def test_accounted_response_is_transparent_and_runs_fastapi_attached_background(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, _trace, store, _records, _logger = _coordinator(monkeypatch)
    wrapped = JSONResponse({"ok": True}, headers={"x-original": "yes"})
    completion.mark_response_ready(wrapped.status_code)
    response = _AccountedResponse(wrapped, completion)
    background_calls: list[tuple[str, int | None]] = []

    def observe_background() -> None:
        live = store.snapshot()
        background_calls.append(("ran", live[0].downstream_bytes))

    response.background = BackgroundTask(observe_background)
    response.headers["x-added"] = "yes"
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(dict(message))

    assert isinstance(response, Response)
    assert response.status_code == wrapped.status_code
    assert response.media_type == wrapped.media_type
    assert response.charset == wrapped.charset
    assert response.body == wrapped.body
    assert response.raw_headers is wrapped.raw_headers
    assert response.background is wrapped.background

    await response(HTTP_SCOPE, receive_request, send)

    assert background_calls == [("ran", len(wrapped.body))]
    assert wrapped.headers["x-added"] == "yes"
    assert sent[0]["type"] == "http.response.start"
    assert sent[-1]["type"] == "http.response.body"
    record = store.observation_snapshot().completed[-1]
    assert record.status == "ok"
    assert record.delivery.state is DeliveryState.ACCEPTED
    assert record.delivery.unit == "body"
    assert record.delivery.downstream_body_bytes == len(wrapped.body)


@pytest.mark.asyncio
async def test_status_mutation_is_reflected_in_wire_legacy_and_delivery_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, _trace, store, _records, _logger = _coordinator(monkeypatch)
    wrapped = Response(b"body", status_code=200)
    completion.mark_response_ready(200)
    response = _AccountedResponse(wrapped, completion)
    response.status_code = 503
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(dict(message))

    await response(HTTP_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert sent[0]["status"] == 503
    assert record.request_line().status_code == 503
    assert record.delivery.intended_http_status == 503
    assert record.status == "fail"


@pytest.mark.asyncio
async def test_actual_dynamic_start_status_overrides_the_response_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, _trace, store, _records, _logger = _coordinator(monkeypatch)
    wrapped = DynamicStartResponse(status_code=200)
    completion.mark_response_ready(200)
    response = _AccountedResponse(wrapped, completion)

    async def send(_message: Message) -> None:
        pass

    await response(HTTP_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.request_line().status_code == 418
    assert record.delivery.intended_http_status == 418
    assert record.status == "fail"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fail_on", "expected_state"),
    [
        ("http.response.start", DeliveryState.NOT_STARTED),
        ("http.response.body", DeliveryState.STARTED),
    ],
)
async def test_send_origin_oserror_is_gone_at_the_actual_frontier(
    monkeypatch: pytest.MonkeyPatch,
    fail_on: str,
    expected_state: DeliveryState,
) -> None:
    completion, _trace, store, _records, _logger = _coordinator(monkeypatch)
    wrapped = Response(b"body")
    completion.mark_response_ready(200)
    response = _AccountedResponse(wrapped, completion)
    response.status_code = 503

    async def send(message: Message) -> None:
        if message["type"] == fail_on:
            raise OSError("client transport closed")

    with pytest.raises(OSError, match="client transport closed"):
        await response(HTTP_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "gone"
    assert record.delivery.state is expected_state
    assert record.delivery.intended_http_status == 503
    assert record.request_line().status_code == 503
    assert record.delivery.failure is not None
    assert record.delivery.failure.origin is FailureOrigin.SEND
    assert record.delivery.failure.category is FailureCategory.DISCONNECT


@pytest.mark.asyncio
async def test_non_send_oserror_is_a_server_failure_not_a_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, _trace, store, _records, _logger = _coordinator(monkeypatch)
    wrapped = BrokenResponse()
    completion.mark_response_ready(200)
    response = _AccountedResponse(wrapped, completion)

    async def send(_message: Message) -> None:
        raise AssertionError("the broken response never calls send")

    with pytest.raises(OSError, match="local response failed"):
        await response(HTTP_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "fail"
    assert record.delivery.state is DeliveryState.NOT_STARTED
    assert record.delivery.failure is not None
    assert record.delivery.failure.origin is FailureOrigin.WRAPPED
    assert record.delivery.failure.category is FailureCategory.ERROR


@pytest.mark.asyncio
async def test_pathsend_is_a_valid_terminal_with_unknown_application_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, _trace, store, _records, _logger = _coordinator(monkeypatch)
    wrapped = PathsendResponse()
    completion.mark_response_ready(200)
    response = _AccountedResponse(wrapped, completion)

    async def send(_message: Message) -> None:
        pass

    await response(HTTP_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "ok"
    assert record.delivery.state is DeliveryState.ACCEPTED
    assert record.delivery.unit == "pathsend"
    assert record.delivery.downstream_body_bytes is None


@pytest.mark.asyncio
async def test_a_response_returning_without_a_terminal_is_recorded_as_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, _trace, store, _records, _logger = _coordinator(monkeypatch)
    wrapped = MissingTerminalResponse()
    completion.mark_response_ready(200)
    response = _AccountedResponse(wrapped, completion)

    async def send(_message: Message) -> None:
        pass

    await response(HTTP_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "fail"
    assert record.delivery.state is DeliveryState.STARTED
    assert record.delivery.failure is not None
    assert record.delivery.failure.category is FailureCategory.INCOMPLETE_RESPONSE


@pytest.mark.asyncio
async def test_background_failure_is_post_delivery_and_does_not_rewrite_client_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, _trace, store, _records, _logger = _coordinator(monkeypatch)

    def fail_background() -> None:
        raise RuntimeError("background failed")

    wrapped = Response(b"body", background=BackgroundTask(fail_background))
    completion.mark_response_ready(200)
    response = _AccountedResponse(wrapped, completion)

    async def send(_message: Message) -> None:
        pass

    with pytest.raises(RuntimeError, match="background failed"):
        await response(HTTP_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "ok"
    assert record.delivery.state is DeliveryState.ACCEPTED
    assert record.delivery.failure is None
    assert record.delivery.post_delivery_failure is not None
    assert record.delivery.post_delivery_failure.origin is FailureOrigin.BACKGROUND


@pytest.mark.asyncio
async def test_accepted_custom_response_failure_is_wrapped_not_guessed_as_background(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, _trace, store, _records, _logger = _coordinator(monkeypatch)
    wrapped = AcceptedThenBrokenResponse(status_code=200)
    completion.mark_response_ready(200)
    response = _AccountedResponse(wrapped, completion)

    async def send(_message: Message) -> None:
        pass

    with pytest.raises(RuntimeError, match="wrapped response failed after acceptance"):
        await response(HTTP_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "ok"
    assert record.delivery.post_delivery_failure is not None
    assert record.delivery.post_delivery_failure.origin is FailureOrigin.WRAPPED
    assert record.delivery.additional_failures == ()


@pytest.mark.asyncio
async def test_an_accepted_http_error_remains_an_operator_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, _trace, store, _records, _logger = _coordinator(monkeypatch)
    wrapped = Response(b"no", status_code=404)
    completion.mark_response_ready(404)
    response = _AccountedResponse(wrapped, completion)

    async def send(_message: Message) -> None:
        pass

    await response(HTTP_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "fail"
    assert record.delivery.state is DeliveryState.ACCEPTED


def test_implicit_settle_preserves_an_observed_zero_byte_upstream_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, trace, _store, _records, _logger = _coordinator(monkeypatch)
    trace.received = 0
    trace.received_known = True

    record = completion.publish()

    assert record.request_line().bytes_out == 0
    assert record.body_bytes.upstream_response == 0


def test_unconsumed_stream_status_body_is_unknown_not_an_observed_empty_body() -> None:
    unconsumed = UpstreamError(
        "stream status",
        status_code=429,
        body_bytes=b"",
        body_observed=False,
    )
    observed_empty = UpstreamError(
        "buffered status",
        status_code=429,
        body_bytes=b"",
        body_observed=True,
    )

    assert _upstream_error_body(unconsumed) is None
    assert _upstream_error_body(observed_empty) == b""


def test_provider_usage_integer_beyond_javascript_precision_survives_finalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, trace, _store, records, _logger = _coordinator(monkeypatch)
    value = 10**100
    observer = ResponsesObserver()
    observer.observe_event(
        SseEvent(
            event="response.completed",
            data=(
                '{"type":"response.completed","copilot_usage":{"opaque":'
                f"{value}"
                '},"response":{"status":"completed","usage":{"input_tokens":'
                f"{value}"
                ',"input_tokens_details":{"cached_tokens":0,"cache_write_tokens":0},'
                '"output_tokens":1,"total_tokens":'
                f"{value + 1}"
                "}}}"
            ),
        )
    )
    trace.absorb_response(observer.snapshot())
    completion.mark_response_ready(200)
    completion.note_asgi_message_sent({"type": "http.response.start", "status": 200})
    completion.note_asgi_message_sent({"type": "http.response.body", "body": b"ok"})
    completion.settle(status_code=200, upstream_response_bytes=2)

    record = completion.publish()

    assert record.request_line().usage["input_tokens"] == value
    response = cast(dict[str, Any], cast(dict[str, Any], records[0]["observation"])["response"])
    usage = cast(dict[str, Any], response["usage"])
    exact = cast(dict[str, Any], usage["exact"])
    assert exact["upstream_input_tokens"] == value
    raw_value = cast(dict[str, Any], cast(dict[str, Any], usage["raw"])["value"])
    assert type(raw_value["input_tokens"]) is int
    assert raw_value["input_tokens"] == value
    provider_value = cast(
        dict[str, Any],
        cast(dict[str, Any], response["provider_usage"])["value"],
    )
    assert type(provider_value["opaque"]) is int
    assert provider_value["opaque"] == value


@pytest.mark.asyncio
async def test_legacy_freeze_failure_does_not_replace_a_primary_send_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    completion, trace, store, records, logger = _coordinator(monkeypatch)
    trace.usage = {"unsupported": object()}
    wrapped = Response(b"body")
    completion.mark_response_ready(200)
    response = _AccountedResponse(wrapped, completion)

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            raise OSError("client transport closed")

    with pytest.raises(OSError, match="client transport closed"):
        await response(HTTP_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "gone"
    assert record.delivery.failure is not None
    assert record.delivery.failure.message == "client transport closed"
    assert record.request_line().detail == "request observability degraded: FrozenJsonError"
    assert len(records) == 1
    assert len(logger.events) == 1
    assert "could not freeze the full legacy request projection" in caplog.text


@pytest.mark.asyncio
async def test_memoryview_response_body_counts_at_the_send_frontier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, _trace, store, _records, _logger = _coordinator(monkeypatch)
    wrapped = Response(memoryview(b"body"))
    completion.mark_response_ready(200)
    response = _AccountedResponse(wrapped, completion)

    async def send(_message: Message) -> None:
        pass

    await response(HTTP_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.delivery.downstream_body_bytes == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fail_on", "expected_state"),
    [
        ("http.response.start", DeliveryState.NOT_STARTED),
        ("http.response.body", DeliveryState.STARTED),
    ],
)
async def test_non_disconnect_send_failure_is_a_server_failure_at_either_frontier(
    monkeypatch: pytest.MonkeyPatch,
    fail_on: str,
    expected_state: DeliveryState,
) -> None:
    completion, _trace, store, _records, _logger = _coordinator(monkeypatch)
    wrapped = Response(b"body")
    completion.mark_response_ready(200)
    response = _AccountedResponse(wrapped, completion)

    async def send(message: Message) -> None:
        if message["type"] == fail_on:
            raise RuntimeError("ASGI server send failed")

    with pytest.raises(RuntimeError, match="ASGI server send failed"):
        await response(HTTP_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "fail"
    assert record.delivery.state is expected_state
    assert record.delivery.failure is not None
    assert record.delivery.failure.origin is FailureOrigin.SEND
    assert record.delivery.failure.category is FailureCategory.ERROR


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("after_start", "expected_state"),
    [(False, DeliveryState.NOT_STARTED), (True, DeliveryState.STARTED)],
)
async def test_wrapped_cancellation_is_gone_before_acceptance(
    monkeypatch: pytest.MonkeyPatch,
    after_start: bool,
    expected_state: DeliveryState,
) -> None:
    completion, _trace, store, _records, _logger = _coordinator(monkeypatch)
    wrapped = CancelledResponse(after_start=after_start)
    completion.mark_response_ready(200)
    response = _AccountedResponse(wrapped, completion)

    async def send(_message: Message) -> None:
        pass

    with pytest.raises(asyncio.CancelledError, match="wrapped response cancelled"):
        await response(HTTP_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "gone"
    assert record.delivery.state is expected_state
    assert record.delivery.failure is not None
    assert record.delivery.failure.origin is FailureOrigin.WRAPPED
    assert record.delivery.failure.category is FailureCategory.CANCELLED


@pytest.mark.asyncio
async def test_provider_failure_wins_over_a_pre_acceptance_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, trace, store, _records, _logger = _coordinator(monkeypatch)
    observer = ResponsesObserver()
    observer.observe_response({
        "status": "failed",
        "error": {"code": "provider_failed", "message": "provider rejected the response"},
    })
    trace.absorb_response(observer.snapshot())
    wrapped = Response(b"provider body")
    completion.mark_response_ready(200)
    response = _AccountedResponse(wrapped, completion)

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            raise OSError("client transport closed")

    with pytest.raises(OSError, match="client transport closed"):
        await response(HTTP_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "fail"
    assert record.response is not None and record.response.provider_failed
    assert record.delivery.state is DeliveryState.STARTED
    assert record.delivery.failure is not None
    assert record.delivery.failure.category is FailureCategory.DISCONNECT


@pytest.mark.asyncio
async def test_an_accepted_provider_failure_is_not_relabelled_from_http_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, trace, store, _records, _logger = _coordinator(monkeypatch)
    observer = ResponsesObserver()
    observer.observe_response({"status": "cancelled"})
    trace.absorb_response(observer.snapshot())
    wrapped = Response(b"provider body")
    completion.mark_response_ready(200)
    response = _AccountedResponse(wrapped, completion)

    async def send(_message: Message) -> None:
        pass

    await response(HTTP_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "fail"
    assert record.delivery.state is DeliveryState.ACCEPTED
    assert record.delivery.failure is None


def test_secondary_unwind_failure_does_not_replace_the_primary_delivery_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, _trace, _store, _records, _logger = _coordinator(monkeypatch)
    completion.note_send_failure(OSError("client transport closed"))
    completion.note_wrapped_failure(
        RuntimeError("cleanup also failed"),
        origin=FailureOrigin.CLEANUP,
    )
    completion.settle(status_code=200, upstream_response_bytes=13)

    record = completion.publish()

    assert record.status == "gone"
    assert record.delivery.failure is not None
    assert record.delivery.failure.origin is FailureOrigin.SEND
    assert record.delivery.failure.message == "client transport closed"


@pytest.mark.asyncio
async def test_stream_cleanup_failure_does_not_replace_a_send_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, trace, store, _records, _logger = _coordinator(monkeypatch)

    async def body() -> AsyncGenerator[bytes]:
        try:
            yield b"chunk"
        finally:
            raise RuntimeError("inner cleanup failed")

    accounting = _StreamAccounting(
        chain=completion.chain,
        request_id=trace.request_id,
        trace=trace,
        completion=completion,
        status_code=200,
    )
    content = _tracked_delivery(body(), accounting)
    response = _AccountedStreamingResponse(content, accounting, status_code=200)
    completion.mark_response_ready(200)

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            raise OSError("client transport closed")

    with pytest.raises(ClientDisconnect) as raised:
        await response(STREAM_SCOPE, receive_request, send)

    assert isinstance(raised.value.__cause__, RuntimeError)
    assert str(raised.value.__cause__) == "inner cleanup failed"
    record = store.observation_snapshot().completed[-1]
    assert record.status == "gone"
    assert record.delivery.state is DeliveryState.STARTED
    assert record.delivery.failure is not None
    assert record.delivery.failure.origin is FailureOrigin.SEND
    assert record.delivery.failure.category is FailureCategory.DISCONNECT
    assert record.delivery.failure.message == "client transport closed"


@pytest.mark.asyncio
async def test_accepted_native_terminal_survives_later_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, trace, store, _records, _logger = _coordinator(monkeypatch)
    terminal_sent = asyncio.Event()
    hold_tail = asyncio.Event()
    assembler = responses_passthrough_assembler()
    assembler.push(
        SseEvent(
            event="response.completed",
            data='{"type":"response.completed","response":{"status":"completed","output":[],"usage":{"input_tokens":0,"output_tokens":0}}}',
        )
    )
    assert assembler.terminal.stop_reason == "end_turn"

    async def body() -> AsyncGenerator[bytes]:
        accounting.completion_delivery.offer()
        try:
            yield b"terminal"
            await hold_tail.wait()
        finally:
            raise RuntimeError("transport tail cleanup failed")

    accounting = _StreamAccounting(
        chain=completion.chain,
        request_id=trace.request_id,
        trace=trace,
        completion=completion,
        status_code=200,
        assembler=cast(Any, assembler),
        passthrough=True,
    )
    content = _tracked_delivery(body(), accounting)
    response = _AccountedStreamingResponse(content, accounting, status_code=200)
    completion.mark_response_ready(200)

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and message.get("body") == b"terminal":
            terminal_sent.set()

    async def receive() -> Message:
        await terminal_sent.wait()
        return {"type": "http.disconnect"}

    await response(HTTP_SCOPE, receive, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "ok", (
        record.delivery,
        record.request_line(),
        accounting.failure,
        accounting.drained,
        accounting.completion_delivery,
    )
    assert record.delivery.state is DeliveryState.ACCEPTED
    assert record.delivery.unit == "native_terminal_batch"
    assert record.delivery.failure is None
    assert record.delivery.post_delivery_failure is not None
    assert record.delivery.post_delivery_failure.origin is FailureOrigin.CLEANUP
    assert record.delivery.post_delivery_failure.message == "transport tail cleanup failed"


@pytest.mark.asyncio
async def test_pre_acceptance_cancellation_remains_primary_when_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, trace, store, _records, _logger = _coordinator(monkeypatch)
    nonterminal_sent = asyncio.Event()
    hold_tail = asyncio.Event()

    async def body() -> AsyncGenerator[bytes]:
        try:
            yield b"nonterminal"
            await hold_tail.wait()
        finally:
            raise RuntimeError("transport tail cleanup failed")

    accounting = _StreamAccounting(
        chain=completion.chain,
        request_id=trace.request_id,
        trace=trace,
        completion=completion,
        status_code=200,
        assembler=cast(Any, responses_passthrough_assembler()),
        passthrough=True,
    )
    content = _tracked_delivery(body(), accounting)
    response = _AccountedStreamingResponse(content, accounting, status_code=200)
    completion.mark_response_ready(200)

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and message.get("body") == b"nonterminal":
            nonterminal_sent.set()

    async def receive() -> Message:
        await nonterminal_sent.wait()
        return {"type": "http.disconnect"}

    await response(HTTP_SCOPE, receive, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "gone"
    assert record.delivery.state is DeliveryState.STARTED
    assert record.delivery.failure is not None
    assert record.delivery.failure.origin is FailureOrigin.WRAPPED
    assert record.delivery.failure.category is FailureCategory.CANCELLED
    assert record.delivery.post_delivery_failure is None
    assert len(record.delivery.additional_failures) == 1
    assert record.delivery.additional_failures[0].origin is FailureOrigin.CLEANUP
    detail = record.request_line().detail
    assert "delivery stopped before upstream finished" in detail
    assert "cleanup also failed: transport tail cleanup failed" in detail


@pytest.mark.asyncio
async def test_stream_start_failure_publishes_without_starting_the_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, trace, store, records, logger = _coordinator(monkeypatch)
    trace.response_observation = None
    context = RequestContext(
        inbound_format=WireFormat.OPENAI_RESPONSES,
        requested_model="gpt-model",
        payload={},
        target_format=WireFormat.OPENAI_RESPONSES,
    )
    context.begin_attempt()
    body_started = False

    async def body() -> AsyncGenerator[bytes]:
        nonlocal body_started
        body_started = True
        yield b"never sent"

    accounting = _StreamAccounting(
        chain=completion.chain,
        request_id=trace.request_id,
        trace=trace,
        completion=completion,
        status_code=200,
        context=context,
    )
    content = _tracked_delivery(
        one_shot_delivery(
            body(),
            on_complete=accounting.completion_delivery.offer,
        ),
        accounting,
    )
    close_calls: list[int] = []

    async def close_response() -> None:
        close_calls.append(len(records))

    response = _AccountedStreamingResponse(
        content,
        accounting,
        status_code=200,
        close_response=close_response,
    )
    completion.mark_response_ready(200)

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            raise OSError("client transport closed")

    with pytest.raises(ClientDisconnect):
        await response(STREAM_SCOPE, receive_request, send)

    assert body_started is False
    assert close_calls == [0], "the response owner must close before publication"
    snapshot = store.observation_snapshot()
    assert snapshot.live == ()
    assert len(snapshot.completed) == 1
    record = snapshot.completed[0]
    assert record.status == "gone"
    assert record.delivery.state is DeliveryState.NOT_STARTED
    assert record.delivery.failure is not None
    assert record.delivery.failure.origin is FailureOrigin.SEND
    assert record.response is not None
    assert record.response.availability is ResponseAvailability.UNAVAILABLE
    assert [issue.code for issue in record.response.issues] == [
        "provider_body_not_observed"
    ]
    assert len(records) == 1
    assert len(logger.events) == 1


@pytest.mark.asyncio
async def test_stream_start_server_failure_keeps_its_primary_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, trace, store, _records, _logger = _coordinator(monkeypatch)

    async def body() -> AsyncGenerator[bytes]:
        yield b"never sent"

    accounting = _StreamAccounting(
        chain=completion.chain,
        request_id=trace.request_id,
        trace=trace,
        completion=completion,
        status_code=200,
    )
    content = _tracked_delivery(body(), accounting)
    response = _AccountedStreamingResponse(content, accounting, status_code=200)
    completion.mark_response_ready(200)

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            raise RuntimeError("ASGI server could not start response")

    with pytest.raises(RuntimeError, match="ASGI server could not start response"):
        await response(STREAM_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "fail"
    assert record.delivery.failure is not None
    assert record.delivery.failure.message == "ASGI server could not start response"
    assert record.request_line().detail == "ASGI server could not start response"


@pytest.mark.asyncio
@pytest.mark.parametrize("reported_failure", [False, True])
async def test_drained_native_non_completion_waits_for_the_final_asgi_body(
    monkeypatch: pytest.MonkeyPatch,
    reported_failure: bool,
) -> None:
    completion, trace, store, _records, _logger = _coordinator(monkeypatch)
    assembler = responses_passthrough_assembler()
    if reported_failure:
        assembler.push(
            SseEvent(
                event="response.failed",
                data='{"type":"response.failed","response":{"error":{"code":"broken","message":"boom"}}}',
            )
        )

    async def body() -> AsyncGenerator[bytes]:
        yield b"native failure or unterminated body"

    accounting = _StreamAccounting(
        chain=completion.chain,
        request_id=trace.request_id,
        trace=trace,
        completion=completion,
        status_code=200,
        assembler=cast(Any, assembler),
        passthrough=True,
    )
    content = _tracked_delivery(body(), accounting)
    response = _AccountedStreamingResponse(content, accounting, status_code=200)
    completion.mark_response_ready(200)

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and not bool(message.get("more_body", False)):
            raise OSError("final empty body send disconnected")

    with pytest.raises(ClientDisconnect):
        await response(STREAM_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "fail"
    assert record.delivery.state is DeliveryState.STARTED
    assert record.delivery.unit is None
    assert record.delivery.failure is not None
    assert record.delivery.failure.origin is FailureOrigin.SEND
    assert record.delivery.failure.category is FailureCategory.DISCONNECT
    assert record.delivery.post_delivery_failure is None


@pytest.mark.parametrize(
    "origin",
    [StreamFailureOrigin.UPSTREAM_EVENT, StreamFailureOrigin.PROXY_REFUSAL],
)
def test_reported_stream_failure_outranks_an_earlier_send_disconnect(
    monkeypatch: pytest.MonkeyPatch,
    origin: StreamFailureOrigin,
) -> None:
    completion, trace, _store, _records, _logger = _coordinator(monkeypatch)
    reported = StreamFailure(
        event="response.failed" if origin is StreamFailureOrigin.UPSTREAM_EVENT else "",
        raw_data='{"type":"response.failed"}' if origin is StreamFailureOrigin.UPSTREAM_EVENT else "",
        info=ErrorInfo(
            category=ErrorCategory.UPSTREAM,
            message="reported stream failure",
            status_code=502,
            code="stream_failed",
        ),
        origin=origin,
    )
    assembler = cast(
        Any,
        SimpleNamespace(
            terminal=Terminal(),
            failure=reported,
        ),
    )
    accounting = _StreamAccounting(
        chain=completion.chain,
        request_id=trace.request_id,
        trace=trace,
        completion=completion,
        status_code=200,
        assembler=assembler,
        passthrough=True,
    )
    completion.mark_response_ready(200)
    completion.note_asgi_message_sent({"type": "http.response.start", "status": 200})
    completion.note_send_failure(OSError("client transport closed"))

    accounting.settle()
    record = completion.publish()

    assert record.status == "fail"
    assert "reported stream failure" in record.request_line().detail
    assert record.delivery.failure is not None
    assert record.delivery.failure.category is FailureCategory.DISCONNECT


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_semantic_send", [False, True])
async def test_empty_one_shot_body_crosses_only_after_its_own_send_returns(
    monkeypatch: pytest.MonkeyPatch,
    fail_semantic_send: bool,
) -> None:
    completion, trace, store, _records, _logger = _coordinator(monkeypatch)

    async def empty_body() -> AsyncGenerator[bytes]:
        if False:
            yield b""

    accounting = _StreamAccounting(
        chain=completion.chain,
        request_id=trace.request_id,
        trace=trace,
        completion=completion,
        status_code=200,
    )
    content = _tracked_delivery(
        one_shot_delivery(
            empty_body(),
            on_complete=accounting.completion_delivery.offer,
        ),
        accounting,
    )
    response = _AccountedStreamingResponse(content, accounting, status_code=200)
    completion.mark_response_ready(200)
    body_sends = 0

    async def send(message: Message) -> None:
        nonlocal body_sends
        if message["type"] != "http.response.body":
            return
        body_sends += 1
        if fail_semantic_send and bool(message.get("more_body", False)):
            raise OSError("empty one-shot send failed")

    if fail_semantic_send:
        with pytest.raises(ClientDisconnect):
            await response(STREAM_SCOPE, receive_request, send)
    else:
        await response(STREAM_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    if fail_semantic_send:
        assert body_sends == 1
        assert record.status == "gone"
        assert record.delivery.state is DeliveryState.STARTED
        assert record.delivery.unit is None
        assert record.delivery.failure is not None
        assert record.delivery.failure.origin is FailureOrigin.SEND
    else:
        assert body_sends == 2
        assert record.status == "ok"
        assert record.delivery.state is DeliveryState.ACCEPTED
        assert record.delivery.unit == "one_shot_body"
        assert record.delivery.downstream_body_bytes == 0


@pytest.mark.asyncio
async def test_final_empty_stream_send_failure_is_a_late_fact_after_natural_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, trace, store, records, logger = _coordinator(monkeypatch)

    async def body() -> AsyncGenerator[bytes]:
        yield b"chunk"

    accounting = _StreamAccounting(
        chain=completion.chain,
        request_id=trace.request_id,
        trace=trace,
        completion=completion,
        status_code=200,
    )
    content = _tracked_delivery(
        one_shot_delivery(
            body(),
            on_complete=accounting.completion_delivery.offer,
        ),
        accounting,
    )
    response = _AccountedStreamingResponse(content, accounting, status_code=200)
    completion.mark_response_ready(200)

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and not bool(message.get("more_body", False)):
            raise RuntimeError("final empty body send failed")

    with pytest.raises(RuntimeError, match="final empty body send failed"):
        await response(STREAM_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "ok"
    assert record.delivery.state is DeliveryState.ACCEPTED
    assert record.delivery.unit == "one_shot_body"
    assert record.delivery.failure is None
    assert record.delivery.post_delivery_failure is not None
    assert record.delivery.post_delivery_failure.origin is FailureOrigin.SEND
    assert record.delivery.downstream_body_bytes == len(b"chunk")
    assert len(records) == 1
    assert len(logger.events) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(RuntimeError("stream background failed"), id="exception"),
        pytest.param(asyncio.CancelledError("stream background cancelled"), id="cancellation"),
    ],
)
async def test_stream_background_failure_is_a_late_fact_after_natural_drain(
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    completion, trace, store, records, logger = _coordinator(monkeypatch)

    async def body() -> AsyncGenerator[bytes]:
        yield b"chunk"

    async def fail_background() -> None:
        raise failure

    accounting = _StreamAccounting(
        chain=completion.chain,
        request_id=trace.request_id,
        trace=trace,
        completion=completion,
        status_code=200,
    )
    content = _tracked_delivery(
        one_shot_delivery(
            body(),
            on_complete=accounting.completion_delivery.offer,
        ),
        accounting,
    )
    response = _AccountedStreamingResponse(
        content,
        accounting,
        status_code=200,
        background=BackgroundTask(fail_background),
    )
    completion.mark_response_ready(200)

    async def send(_message: Message) -> None:
        pass

    with pytest.raises(type(failure), match=str(failure)):
        await response(STREAM_SCOPE, receive_request, send)

    record = store.observation_snapshot().completed[-1]
    assert record.status == "ok"
    assert record.delivery.state is DeliveryState.ACCEPTED
    assert record.delivery.failure is None
    assert record.delivery.post_delivery_failure is not None
    assert record.delivery.post_delivery_failure.origin is FailureOrigin.BACKGROUND
    expected_category = (
        FailureCategory.CANCELLED
        if isinstance(failure, asyncio.CancelledError)
        else FailureCategory.ERROR
    )
    assert record.delivery.post_delivery_failure.category is expected_category
    assert len(records) == 1
    assert len(logger.events) == 1


@pytest.mark.asyncio
async def test_background_and_cleanup_failures_both_reach_the_final_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion, trace, store, records, logger = _coordinator(monkeypatch)

    async def body() -> AsyncGenerator[bytes]:
        yield b"chunk"

    async def fail_background() -> None:
        raise RuntimeError("background failed first")

    async def fail_cleanup() -> None:
        raise OSError("cleanup failed second")

    accounting = _StreamAccounting(
        chain=completion.chain,
        request_id=trace.request_id,
        trace=trace,
        completion=completion,
        status_code=200,
    )
    content = _tracked_delivery(
        one_shot_delivery(
            body(),
            on_complete=accounting.completion_delivery.offer,
        ),
        accounting,
    )
    response = _AccountedStreamingResponse(
        content,
        accounting,
        status_code=200,
        background=BackgroundTask(fail_background),
        close_response=fail_cleanup,
    )
    completion.mark_response_ready(200)

    async def send(_message: Message) -> None:
        pass

    with pytest.raises(RuntimeError, match="background failed first") as raised:
        await response(STREAM_SCOPE, receive_request, send)

    assert isinstance(raised.value.__cause__, OSError)
    assert str(raised.value.__cause__) == "cleanup failed second"
    record = store.observation_snapshot().completed[-1]
    assert record.status == "ok"
    assert record.delivery.post_delivery_failure is not None
    assert record.delivery.post_delivery_failure.origin is FailureOrigin.BACKGROUND
    assert len(record.delivery.additional_failures) == 1
    assert record.delivery.additional_failures[0].origin is FailureOrigin.CLEANUP
    assert record.delivery.additional_failures[0].message == "cleanup failed second"
    delivery = cast(
        dict[str, Any],
        cast(dict[str, Any], records[0]["observation"])["delivery"],
    )
    additional = cast(list[dict[str, Any]], delivery["additional_failures"])
    assert additional[0]["origin"] == "cleanup"
    assert len(logger.events) == 1
