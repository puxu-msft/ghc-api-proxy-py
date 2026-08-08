from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import httpx
import orjson
import pytest
from anthropic.types import Message as SdkMessage
from pydantic import TypeAdapter

from app.anthropic.client import AnthropicClient
from app.config.settings import AppSettings
from app.errors import ApiError
from app.history.consumer import HistoryConsumer
from app.history.store import HistoryStore
from app.hooks.builtin import register_builtin_hooks
from app.hooks.context import HookContext
from app.hooks.executor import HooksExecutor
from app.hooks.registry import HookRegistryBuilder
from app.hooks.types import (
    HookErrorMode,
    ObserverEvent,
    ResponseHook,
    ResponseHookResult,
    RetryStrategyFactory,
)
from app.models.anthropic import MessagesRequest
from app.pipeline.context import RequestContext, RequestState
from app.pipeline.executor import UpstreamResponseError, execute_anthropic_pipeline
from app.pipeline.rate_limiter import AdaptiveRateLimiter
from app.pipeline.strategies import RetryDecision
from app.tokenization.state_store import TokenizationStateStore
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
        del payload, extra_headers
        request = httpx.Request("POST", "https://upstream.test/v1/messages")
        if self.status_code == 200 and not stream:
            return httpx.Response(
                self.status_code,
                request=request,
                json={
                    "id": "msg_component",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-test",
                    "content": [{"type": "text", "text": "ok"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            )
        return httpx.Response(
            self.status_code,
            request=request,
            stream=Stream(),
        )


class ResponsesTarget:
    def __init__(self, response_body: dict[str, Any]) -> None:
        self.response_body = response_body
        self.calls = 0

    async def send_anthropic(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        del payload, stream, extra_headers
        raise AssertionError("Responses route must not call the Messages transport")

    async def send_responses(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx.Response:
        del payload, stream
        self.calls += 1
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://upstream.test/responses"),
            json=self.response_body,
        )


class RetryingResponsesTarget(ResponsesTarget):
    async def send_responses(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx.Response:
        del payload, stream
        self.calls += 1
        request = httpx.Request("POST", "https://upstream.test/responses")
        if self.calls == 1:
            return httpx.Response(
                429,
                request=request,
                json={"error": {"message": "retry", "code": "rate_limit"}},
            )
        return httpx.Response(200, request=request, json=self.response_body)


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
    commit_order: list[str] | None = None

    async def observe(
        self,
        event: ObserverEvent,
        context: HookContext,
        data: Mapping[str, Any],
    ) -> None:
        del context, data
        self.seen.append(event)
        if event is ObserverEvent.RESPONSE and self.commit_order is not None:
            self.commit_order.append("response")


@dataclass(frozen=True, slots=True)
class ReplaceResponseTextHook:
    name: str = "replace-response-text"
    order: int = 1000
    error_mode: HookErrorMode = HookErrorMode.FAIL_REQUEST

    async def transform(
        self,
        body: bytes,
        status_code: int,
        context: HookContext,
    ) -> ResponseHookResult:
        del status_code, context
        parsed = cast(object, orjson.loads(body))
        assert isinstance(parsed, dict)
        content = cast(object, parsed["content"])
        assert isinstance(content, list)
        block = cast(object, content[0])
        assert isinstance(block, dict)
        block["text"] = "hooked"
        return ResponseHookResult(orjson.dumps(parsed), True, ("replace-text",))


@dataclass(frozen=True, slots=True)
class InvalidResponseHook:
    name: str = "invalidate-response"
    order: int = 1000
    error_mode: HookErrorMode = HookErrorMode.FAIL_REQUEST

    async def transform(
        self,
        body: bytes,
        status_code: int,
        context: HookContext,
    ) -> ResponseHookResult:
        del body, status_code, context
        return ResponseHookResult(b"{}", False, ())


@dataclass(frozen=True, slots=True)
class FixedResponseHook:
    body: bytes
    name: str = "fixed-response"
    order: int = 1000
    error_mode: HookErrorMode = HookErrorMode.FAIL_REQUEST

    async def transform(
        self,
        body: bytes,
        status_code: int,
        context: HookContext,
    ) -> ResponseHookResult:
        del body, status_code, context
        return ResponseHookResult(self.body, True, ("replace-response",))


@dataclass(frozen=True, slots=True)
class ReplaceResponseUsageHook:
    input_tokens: int
    name: str = "replace-response-usage"
    order: int = 1000
    error_mode: HookErrorMode = HookErrorMode.FAIL_REQUEST

    async def transform(
        self,
        body: bytes,
        status_code: int,
        context: HookContext,
    ) -> ResponseHookResult:
        del status_code, context
        parsed = cast(object, orjson.loads(body))
        assert isinstance(parsed, dict)
        parsed["usage"] = {
            "input_tokens": self.input_tokens,
            "output_tokens": 1,
        }
        return ResponseHookResult(orjson.dumps(parsed), True, ("replace-usage",))


@dataclass(frozen=True, slots=True)
class RaisingResponseHook:
    name: str = "raising-response"
    order: int = 1000
    error_mode: HookErrorMode = HookErrorMode.FAIL_REQUEST

    async def transform(
        self,
        body: bytes,
        status_code: int,
        context: HookContext,
    ) -> ResponseHookResult:
        del body, status_code, context
        raise RuntimeError("response hook failed")


@dataclass(slots=True)
class RecordingSuccessStrategy:
    name: str = "record-success"
    success_calls: int = 0
    commit_order: list[str] | None = None

    def can_handle(self, error: ApiError) -> bool:
        del error
        return False

    async def handle(
        self,
        error: ApiError,
        payload: dict[str, object],
    ) -> RetryDecision:
        del error
        return RetryDecision(False, payload)

    def on_success(self) -> None:
        self.success_calls += 1
        if self.commit_order is not None:
            self.commit_order.append("strategy")


@dataclass(slots=True)
class RaisingSuccessStrategy(RecordingSuccessStrategy):
    name: str = "raise-on-success"

    def on_success(self) -> None:
        super().on_success()
        raise RuntimeError("strategy success failed")


@dataclass(slots=True)
class RetryOnceStrategy(RecordingSuccessStrategy):
    name: str = "retry-once"
    retry_calls: int = 0

    def can_handle(self, error: ApiError) -> bool:
        return error.status_code == 429 and self.retry_calls == 0

    async def handle(
        self,
        error: ApiError,
        payload: dict[str, object],
    ) -> RetryDecision:
        del error
        self.retry_calls += 1
        return RetryDecision(True, payload, ("retry-once",))


@dataclass(frozen=True, slots=True)
class RecordingSuccessStrategyFactory:
    strategy: RecordingSuccessStrategy
    name: str = "record-success-factory"
    order: int = 1000

    def create(self, context: HookContext) -> RecordingSuccessStrategy:
        del context
        return self.strategy


class RecordingLimiter(AdaptiveRateLimiter):
    def __init__(
        self,
        history: RecordingHistory,
        *,
        commit_order: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._history = history
        self._commit_order = commit_order
        self.success_calls = 0
        self.facts_at_success: tuple[object, ...] = ()

    def report_success(self) -> None:
        self.success_calls += 1
        self.facts_at_success = self._history.started_contexts[0].conversion_facts
        if self._commit_order is not None:
            self._commit_order.append("limiter")
        super().report_success()


class FailingBodyStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        raise httpx.ReadError("body read failed")
        yield b""  # pragma: no cover


class FailingBodyTarget:
    async def send_anthropic(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        del payload, stream, extra_headers
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://upstream.test/v1/messages"),
            stream=FailingBodyStream(),
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


def _responses_client(
    target: ResponsesTarget,
    history: HistoryConsumer | RecordingHistory,
    response_hook: ResponseHook,
    *,
    retry_factory: RetryStrategyFactory | None = None,
    tokenization_state: TokenizationStateStore | None = None,
    observer: RecordingObserver | None = None,
) -> AnthropicClient:
    catalog = ModelCatalog(None, "https://upstream.test")
    catalog.replace_from_data(
        {
            "object": "list",
            "data": [
                {
                    "id": "claude-test",
                    "vendor": "test",
                    "supported_endpoints": ["/responses"],
                }
            ],
        }
    )
    settings = AppSettings.model_validate(
        {"anthropic": {"route_override": "responses"}}
    )
    builder = HookRegistryBuilder()
    if tokenization_state is not None:
        register_builtin_hooks(
            builder,
            settings,
            quarantine=None,
            tokenization_state=tokenization_state,
        )
    builder.register_response(response_hook)
    if retry_factory is not None:
        builder.register_retry(retry_factory)
    if observer is not None:
        builder.register_observer(observer)
    return AnthropicClient(
        target,
        ModelResolver(available_ids={"claude-test"}, model_overrides={}),
        settings,
        history=cast(Any, history),
        hooks=HooksExecutor(builder.build(), user_timeout_ms=1_000),
        model_catalog=catalog,
    )


def _client_with_success_callbacks(
    target: ResponsesTarget,
    history: RecordingHistory,
    response_hook: ResponseHook,
) -> tuple[AnthropicClient, RecordingLimiter, RecordingSuccessStrategy]:
    strategy = RecordingSuccessStrategy()
    client = _responses_client(
        target,
        history,
        response_hook,
        retry_factory=RecordingSuccessStrategyFactory(strategy),
    )
    return client, RecordingLimiter(history), strategy


def _responses_body() -> dict[str, Any]:
    return {
        "id": "resp_history",
        "model": "claude-test",
        "status": "completed",
        "output": [
            {
                "id": "msg_history",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "original"}],
            }
        ],
        "usage": {
            "input_tokens": 5,
            "output_tokens": 3,
            "total_tokens": 8,
            "input_tokens_details": {
                "cached_tokens": 4,
                "cache_write_tokens": 3,
            },
            "output_tokens_details": {
                "reasoning_tokens": 2,
                "accepted_prediction_tokens": 1,
            },
        },
    }


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


@pytest.mark.asyncio
async def test_responses_success_persists_hooked_response_and_exact_facts(
    tmp_path: Path,
) -> None:
    store = HistoryStore(tmp_path / "history.db")
    await store.start()
    target = ResponsesTarget(_responses_body())
    client = _responses_client(
        target,
        HistoryConsumer(store),
        ReplaceResponseTextHook(),
    )

    try:
        result = await execute_anthropic_pipeline(client, _request())
        entry = await store.get(result.context.id)
        await result.response.aclose()
    finally:
        await store.close()

    assert target.calls == 1
    assert entry is not None
    assert entry.status == "completed"
    assert entry.response is not None
    assert entry.response["content"][0]["text"] == "hooked"
    assert orjson.loads(result.response.content) == entry.response
    TypeAdapter(SdkMessage).validate_python(entry.response)
    assert entry.usage == {
        "input_tokens": 0,
        "cache_read_input_tokens": 4,
        "cache_creation_input_tokens": 3,
        "upstream_input_tokens": 5,
        "output_tokens": 3,
        "reasoning_tokens": 2,
        "total_tokens": 10,
        "upstream_total_tokens": 8,
        "input_tokens_details": {
            "cached_tokens": 4,
            "cache_write_tokens": 3,
        },
        "output_tokens_details": {
            "reasoning_tokens": 2,
            "accepted_prediction_tokens": 1,
        },
        "estimated": False,
        "inconsistent": True,
        "conversion_facts": [
            {
                "provenance": "response",
                "attempt": 0,
                "code": "response_id_transformed",
                "field_path": "id",
            },
            {
                "provenance": "response",
                "attempt": 0,
                "code": "usage_inconsistent",
                "field_path": "usage.input_tokens",
            },
        ],
    }


@pytest.mark.asyncio
async def test_responses_missing_usage_persists_estimated_summary(
    tmp_path: Path,
) -> None:
    store = HistoryStore(tmp_path / "history.db")
    await store.start()
    response_body = _responses_body()
    del response_body["usage"]
    target = ResponsesTarget(response_body)
    client = _responses_client(
        target,
        HistoryConsumer(store),
        ReplaceResponseTextHook(),
    )

    try:
        result = await execute_anthropic_pipeline(client, _request())
        entry = await store.get(result.context.id)
        await result.response.aclose()
    finally:
        await store.close()

    assert entry is not None
    assert entry.usage == {
        "input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
        "estimated": True,
        "inconsistent": False,
        "conversion_facts": [
            {
                "provenance": "response",
                "attempt": 0,
                "code": "response_id_transformed",
                "field_path": "id",
            },
            {
                "provenance": "response",
                "attempt": 0,
                "code": "usage_estimated",
                "field_path": "usage",
            },
        ],
    }


@pytest.mark.asyncio
async def test_invalid_hooked_responses_body_persists_no_success_facts(
    tmp_path: Path,
) -> None:
    store = HistoryStore(tmp_path / "history.db")
    await store.start()
    target = ResponsesTarget(_responses_body())
    client = _responses_client(
        target,
        HistoryConsumer(store),
        InvalidResponseHook(),
    )

    try:
        with pytest.raises(ApiError) as captured:
            await execute_anthropic_pipeline(client, _request())
        entries = await store.list_entries(limit=10)
    finally:
        await store.close()

    assert target.calls == 1
    assert captured.value.code == "invalid_anthropic_response_body"
    assert len(entries) == 1
    assert entries[0].status == "failed"
    assert entries[0].response is None
    assert entries[0].usage is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response_hook",
    [
        RaisingResponseHook(),
        FixedResponseHook(
            orjson.dumps(
                {
                    "id": "msg_bad",
                    "model": "claude-test",
                    "content": [{"type": "text"}],
                }
            )
        ),
        FixedResponseHook(
            orjson.dumps(
                {
                    "id": "msg_bad_second",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-test",
                    "content": [
                        {"type": "text", "text": "valid-first"},
                        {
                            "type": "text",
                            "text": "invalid-second",
                            "id": "mixed",
                        },
                    ],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }
            )
        ),
    ],
    ids=["hook-error", "invalid-final-wire", "invalid-second-block"],
)
async def test_failed_final_response_publishes_no_success_callbacks(
    response_hook: ResponseHook,
) -> None:
    history = RecordingHistory()
    client, limiter, strategy = _client_with_success_callbacks(
        ResponsesTarget(_responses_body()),
        history,
        response_hook,
    )

    with pytest.raises((ApiError, RuntimeError)):
        await execute_anthropic_pipeline(client, _request(), rate_limiter=limiter)

    assert limiter.success_calls == 0
    assert strategy.success_calls == 0
    assert history.finalized_contexts[0].state is RequestState.FAILED


@pytest.mark.asyncio
async def test_body_read_failure_publishes_no_success_callbacks() -> None:
    history = RecordingHistory()
    strategy = RecordingSuccessStrategy()
    builder = HookRegistryBuilder()
    builder.register_retry(RecordingSuccessStrategyFactory(strategy))
    client = AnthropicClient(
        FailingBodyTarget(),
        ModelResolver(available_ids={"claude-test"}, model_overrides={}),
        history=cast(Any, history),
        hooks=HooksExecutor(builder.build(), user_timeout_ms=1_000),
    )
    limiter = RecordingLimiter(history)

    with pytest.raises(ApiError):
        await execute_anthropic_pipeline(client, _request(), rate_limiter=limiter)

    assert limiter.success_calls == 0
    assert strategy.success_calls == 0
    assert history.finalized_contexts[0].state is RequestState.FAILED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response_hook",
    [RaisingResponseHook(), InvalidResponseHook()],
    ids=["hook-error", "invalid-final-wire"],
)
async def test_failed_final_response_does_not_calibrate_builtin_success_observer(
    response_hook: ResponseHook,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = RecordingHistory()
    observer = RecordingObserver()
    state = TokenizationStateStore(tmp_path / "tokenization.json")
    baseline = state.snapshot()
    learn_calls: list[tuple[str, str, int, int]] = []
    real_learn = state.calibration.learn

    def spy_learn(protocol: str, model: str, estimate: int, real: int) -> bool:
        learn_calls.append((protocol, model, estimate, real))
        return real_learn(protocol, model, estimate, real)

    monkeypatch.setattr(state.calibration, "learn", spy_learn)
    client = _responses_client(
        ResponsesTarget(_responses_body()),
        history,
        response_hook,
        tokenization_state=state,
        observer=observer,
    )

    with pytest.raises((ApiError, RuntimeError)):
        await execute_anthropic_pipeline(client, _request())

    assert learn_calls == []
    assert state.snapshot() == baseline
    assert state.dirty is False
    assert history.finalized_contexts[0].state is RequestState.FAILED
    assert observer.seen.count(ObserverEvent.RESPONSE) == 0
    assert observer.seen.count(ObserverEvent.ERROR) == 1
    assert observer.seen.count(ObserverEvent.FINALIZE) == 1


@pytest.mark.asyncio
async def test_body_read_failure_does_not_calibrate_builtin_success_observer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = RecordingHistory()
    observer = RecordingObserver()
    state = TokenizationStateStore(tmp_path / "tokenization.json")
    baseline = state.snapshot()
    learn_calls: list[tuple[str, str, int, int]] = []
    real_learn = state.calibration.learn

    def spy_learn(protocol: str, model: str, estimate: int, real: int) -> bool:
        learn_calls.append((protocol, model, estimate, real))
        return real_learn(protocol, model, estimate, real)

    monkeypatch.setattr(state.calibration, "learn", spy_learn)
    settings = AppSettings()
    builder = HookRegistryBuilder()
    register_builtin_hooks(
        builder,
        settings,
        quarantine=None,
        tokenization_state=state,
    )
    builder.register_observer(observer)
    client = AnthropicClient(
        FailingBodyTarget(),
        ModelResolver(available_ids={"claude-test"}, model_overrides={}),
        settings,
        history=cast(Any, history),
        hooks=HooksExecutor(builder.build(), user_timeout_ms=1_000),
    )

    with pytest.raises(ApiError):
        await execute_anthropic_pipeline(client, _request())

    assert learn_calls == []
    assert state.snapshot() == baseline
    assert state.dirty is False
    assert history.finalized_contexts[0].state is RequestState.FAILED
    assert observer.seen.count(ObserverEvent.RESPONSE) == 0
    assert observer.seen.count(ObserverEvent.ERROR) == 1
    assert observer.seen.count(ObserverEvent.FINALIZE) == 1


@pytest.mark.asyncio
async def test_valid_final_response_calibrates_once_after_success_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = RecordingHistory()
    observer = RecordingObserver()
    state = TokenizationStateStore(tmp_path / "tokenization.json")
    learn_calls: list[tuple[str, str, int, int]] = []
    responses_at_learn: list[object | None] = []
    usage_at_learn: list[object | None] = []
    facts_at_learn: list[tuple[object, ...]] = []
    payloads_at_learn: list[dict[str, Any] | None] = []
    real_learn = state.calibration.learn

    def spy_learn(protocol: str, model: str, estimate: int, real: int) -> bool:
        context = history.started_contexts[0]
        learn_calls.append((protocol, model, estimate, real))
        responses_at_learn.append(context.normalized_response)
        usage_at_learn.append(context.response_usage)
        facts_at_learn.append(context.conversion_facts)
        payloads_at_learn.append(context.final_response_payload)
        return real_learn(protocol, model, estimate, real)

    monkeypatch.setattr(state.calibration, "learn", spy_learn)
    client = _responses_client(
        ResponsesTarget(_responses_body()),
        history,
        ReplaceResponseUsageHook(input_tokens=37),
        tokenization_state=state,
        observer=observer,
    )

    result = await execute_anthropic_pipeline(client, _request())
    final_payload = cast(dict[str, Any], orjson.loads(result.response.content))
    await result.response.aclose()

    assert len(learn_calls) == 1
    assert learn_calls[0][0:2] == ("anthropic", "claude-test")
    assert learn_calls[0][3] == 37
    assert responses_at_learn == [result.context.normalized_response]
    assert responses_at_learn[0] is not None
    assert usage_at_learn == [result.context.response_usage]
    assert usage_at_learn[0] is not None
    assert facts_at_learn == [result.context.conversion_facts]
    assert facts_at_learn[0]
    assert payloads_at_learn == [final_payload]
    assert observer.seen.count(ObserverEvent.RESPONSE) == 1
    assert observer.seen.count(ObserverEvent.ERROR) == 0
    assert observer.seen.count(ObserverEvent.FINALIZE) == 1
    assert state.dirty is True
    calibration = state.snapshot()["calibration"]["anthropic:claude-test"]
    assert sum(bucket["sample_count"] for bucket in calibration["buckets"]) == 1


@pytest.mark.asyncio
async def test_throwing_success_strategy_publishes_only_failure_lifecycle(
    tmp_path: Path,
) -> None:
    history = RecordingHistory()
    observer = RecordingObserver()
    strategy = RaisingSuccessStrategy()
    state = TokenizationStateStore(tmp_path / "tokenization.json")
    baseline = state.snapshot()
    client = _responses_client(
        ResponsesTarget(_responses_body()),
        history,
        ReplaceResponseTextHook(),
        retry_factory=RecordingSuccessStrategyFactory(strategy),
        tokenization_state=state,
        observer=observer,
    )

    with pytest.raises(RuntimeError, match="strategy success failed"):
        await execute_anthropic_pipeline(client, _request())

    assert strategy.success_calls == 1
    assert state.snapshot() == baseline
    assert state.dirty is False
    assert history.finalized_contexts == history.started_contexts
    assert history.finalized_contexts[0].state is RequestState.FAILED
    assert observer.seen.count(ObserverEvent.RESPONSE) == 0
    assert observer.seen.count(ObserverEvent.ERROR) == 1
    assert observer.seen.count(ObserverEvent.FINALIZE) == 1


@pytest.mark.asyncio
async def test_success_callbacks_precede_response_commit_once() -> None:
    history = RecordingHistory()
    commit_order: list[str] = []
    observer = RecordingObserver(commit_order=commit_order)
    strategy = RecordingSuccessStrategy(commit_order=commit_order)
    client = _responses_client(
        ResponsesTarget(_responses_body()),
        history,
        ReplaceResponseTextHook(),
        retry_factory=RecordingSuccessStrategyFactory(strategy),
        observer=observer,
    )
    limiter = RecordingLimiter(history, commit_order=commit_order)

    result = await execute_anthropic_pipeline(client, _request(), rate_limiter=limiter)
    await result.response.aclose()

    assert commit_order == ["strategy", "limiter", "response"]
    assert strategy.success_calls == 1
    assert limiter.success_calls == 1
    assert observer.seen.count(ObserverEvent.RESPONSE) == 1
    assert observer.seen.count(ObserverEvent.FINALIZE) == 1
    assert history.finalized_contexts == [result.context]
    assert result.context.state is RequestState.COMPLETED


@pytest.mark.asyncio
async def test_success_callbacks_publish_once_after_context_facts() -> None:
    history = RecordingHistory()
    client, limiter, strategy = _client_with_success_callbacks(
        ResponsesTarget(_responses_body()),
        history,
        ReplaceResponseTextHook(),
    )

    result = await execute_anthropic_pipeline(client, _request(), rate_limiter=limiter)
    await result.response.aclose()

    assert limiter.success_calls == 1
    assert strategy.success_calls == 1
    assert limiter.facts_at_success == result.context.conversion_facts
    assert limiter.facts_at_success


@pytest.mark.asyncio
async def test_history_preserves_request_and_response_conversion_provenance(
    tmp_path: Path,
) -> None:
    store = HistoryStore(tmp_path / "history.db")
    await store.start()
    request = MessagesRequest.model_validate(
        {
            "model": "claude-test",
            "max_tokens": 100,
            "system": [
                {
                    "type": "text",
                    "text": "system",
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "metadata": {"user_id": "user", "tenant": "not-forwarded"},
            "messages": [{"role": "user", "content": "hello"}],
        }
    )
    original_payload = request.model_dump(mode="json", exclude_none=True)
    client = _responses_client(
        ResponsesTarget(_responses_body()),
        HistoryConsumer(store),
        ReplaceResponseTextHook(),
    )

    try:
        result = await execute_anthropic_pipeline(client, request)
        entry = await store.get(result.context.id)
        await result.response.aclose()
    finally:
        await store.close()

    assert entry is not None
    assert entry.request_payload == original_payload
    assert entry.usage is not None
    assert entry.usage["conversion_facts"] == [
        {
            "provenance": "request",
            "attempt": 0,
            "field_path": "system[0].cache_control",
            "disposition": "degrade",
            "reason": "cache_control_not_supported",
        },
        {
            "provenance": "request",
            "attempt": 0,
            "field_path": "metadata.tenant",
            "disposition": "degrade",
            "reason": "metadata_not_allowlisted",
        },
        {
            "provenance": "response",
            "attempt": 0,
            "code": "response_id_transformed",
            "field_path": "id",
        },
        {
            "provenance": "response",
            "attempt": 0,
            "code": "usage_inconsistent",
            "field_path": "usage.input_tokens",
        },
    ]


@pytest.mark.asyncio
async def test_history_projects_only_final_success_attempt_conversion_facts(
    tmp_path: Path,
) -> None:
    store = HistoryStore(tmp_path / "history.db")
    await store.start()
    target = RetryingResponsesTarget(_responses_body())
    strategy = RetryOnceStrategy()
    request = MessagesRequest.model_validate(
        {
            "model": "claude-test",
            "max_tokens": 100,
            "metadata": {"tenant": "not-forwarded"},
            "messages": [{"role": "user", "content": "hello"}],
        }
    )
    client = _responses_client(
        target,
        HistoryConsumer(store),
        ReplaceResponseTextHook(),
        retry_factory=RecordingSuccessStrategyFactory(strategy),
    )

    try:
        result = await execute_anthropic_pipeline(
            client,
            request,
            rate_limiter=AdaptiveRateLimiter(default_retry_interval=0),
        )
        entry = await store.get(result.context.id)
        await result.response.aclose()
    finally:
        await store.close()

    assert target.calls == 2
    assert strategy.retry_calls == 1
    assert strategy.success_calls == 1
    assert [attempt.status_code for attempt in result.context.attempts] == [429, 200]
    assert entry is not None and entry.usage is not None
    facts = entry.usage["conversion_facts"]
    assert {fact["attempt"] for fact in facts} == {1}
    assert [fact["provenance"] for fact in facts] == [
        "request",
        "response",
        "response",
    ]


@pytest.mark.asyncio
async def test_stream_history_projects_final_attempt_request_facts_without_mutating_payload(
    tmp_path: Path,
) -> None:
    store = HistoryStore(tmp_path / "history.db")
    await store.start()
    target = RetryingResponsesTarget(_responses_body())
    strategy = RetryOnceStrategy()
    request = MessagesRequest.model_validate(
        {
            "model": "claude-test",
            "max_tokens": 100,
            "stream": True,
            "system": [
                {
                    "type": "text",
                    "text": "system",
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "metadata": {"user_id": "user", "tenant": "not-forwarded"},
            "messages": [{"role": "user", "content": "hello"}],
        }
    )
    original_payload = request.model_dump(mode="json", exclude_none=True)
    history = HistoryConsumer(store)
    client = _responses_client(
        target,
        history,
        ReplaceResponseTextHook(),
        retry_factory=RecordingSuccessStrategyFactory(strategy),
    )

    try:
        result = await execute_anthropic_pipeline(
            client,
            request,
            rate_limiter=AdaptiveRateLimiter(default_retry_interval=0),
        )
        result.context.transition(RequestState.COMPLETED)
        await history.finalized(
            result.context,
            response={
                "type": "message",
                "content": [{"type": "text", "text": "streamed"}],
                "delivery": {"complete": True, "uncertain": False},
            },
            usage={"input_tokens": 2, "output_tokens": 1},
        )
        entry = await store.get(result.context.id)
        await result.response.aclose()
    finally:
        await store.close()

    assert target.calls == 2
    assert [attempt.status_code for attempt in result.context.attempts] == [429, 200]
    assert entry is not None
    assert entry.request_payload == original_payload
    assert entry.usage is not None
    assert entry.usage["conversion_facts"] == [
        {
            "provenance": "request",
            "attempt": 1,
            "field_path": "system[0].cache_control",
            "disposition": "degrade",
            "reason": "cache_control_not_supported",
        },
        {
            "provenance": "request",
            "attempt": 1,
            "field_path": "metadata.tenant",
            "disposition": "degrade",
            "reason": "metadata_not_allowlisted",
        },
    ]