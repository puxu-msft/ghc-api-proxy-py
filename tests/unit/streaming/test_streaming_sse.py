import asyncio
from collections.abc import AsyncIterator, Coroutine
from typing import Any

import anyio
import pytest
from starlette.types import Message, Scope

from app.config.settings import TimeoutConfig
from app.streaming.idle_timeout import (
    StreamIdleTimeoutError,
    resolve_stream_idle,
    with_idle_timeout,
)
from app.streaming.openai_sse import parse_sse_json
from app.streaming.sse import (
    create_delayed_sse_response,
    create_sse_response,
    format_sse_event,
    passthrough_bytes,
)


def test_format_sse_event_handles_multiline_data() -> None:
    assert format_sse_event("line1\nline2", event="delta") == (
        b"event: delta\ndata: line1\ndata: line2\n\n"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("split_at", range(1, 23))
async def test_responses_sse_parser_handles_every_crlf_chunk_split(
    split_at: int,
) -> None:
    wire = b'data:{"type":"response.created"}\r\n\r\n'

    async def chunks() -> AsyncIterator[bytes]:
        yield wire[:split_at]
        yield wire[split_at:]

    assert [value async for value in parse_sse_json(chunks())] == [
        {"type": "response.created"}
    ]


@pytest.mark.asyncio
async def test_responses_sse_parser_accepts_data_without_optional_space() -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b'data:{"value":1}\n\n'

    assert [value async for value in parse_sse_json(chunks())] == [{"value": 1}]


@pytest.mark.asyncio
async def test_passthrough_bytes_yields_each_upstream_chunk_immediately() -> None:
    sent = anyio.Event()
    release = anyio.Event()

    async def upstream() -> AsyncIterator[bytes]:
        sent.set()
        yield b"first"
        await release.wait()
        yield b"second"

    stream = passthrough_bytes(upstream())
    assert await anext(stream) == b"first"
    await sent.wait()
    release.set()
    assert await anext(stream) == b"second"


@pytest.mark.asyncio
async def test_passthrough_runs_explicit_cleanup_on_close() -> None:
    cleaned = False

    async def source() -> AsyncIterator[bytes]:
        yield b"first"
        await anyio.sleep_forever()

    async def cleanup() -> None:
        nonlocal cleaned
        cleaned = True

    stream = passthrough_bytes(source(), cleanup=cleanup)
    assert await anext(stream) == b"first"
    await stream.aclose()
    assert cleaned is True


@pytest.mark.asyncio
async def test_delayed_response_shields_checkpoint_cleanup_from_disconnect_cancel() -> None:
    cleanup_started = anyio.Event()
    cleanup_finished = anyio.Event()
    disconnect = anyio.Event()

    async def source() -> AsyncIterator[bytes]:
        try:
            await anyio.sleep_forever()
            yield b"unreachable"
        finally:
            cleanup_started.set()
            await anyio.sleep(0)
            await anyio.sleep(0)
            cleanup_finished.set()

    response = create_delayed_sse_response(source())

    async def receive() -> Message:
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        del message

    scope: Scope = {"type": "http"}
    async with anyio.create_task_group() as task_group:
        task_group.start_soon(response, scope, receive, send)
        disconnect.set()
        await cleanup_started.wait()
        task_group.cancel_scope.cancel()

    assert cleanup_finished.is_set()


@pytest.mark.asyncio
async def test_delayed_response_enters_pull_before_preentry_cancellation_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_started = anyio.Event()
    cleanup_finished = anyio.Event()
    loop = asyncio.get_running_loop()
    first_task = True

    async def source() -> AsyncIterator[bytes]:
        try:
            source_started.set()
            await anyio.sleep_forever()
            yield b"unreachable"
        finally:
            await anyio.sleep(0)
            cleanup_finished.set()

    def cancel_owner_before_pull_runs(
        coroutine: Coroutine[Any, Any, Any],
    ) -> asyncio.Task[Any]:
        nonlocal first_task
        task = loop.create_task(coroutine)
        if first_task:
            first_task = False
            owner = asyncio.current_task()
            assert owner is not None
            owner.cancel()
        return task

    monkeypatch.setattr(asyncio, "create_task", cancel_owner_before_pull_runs)
    response = create_delayed_sse_response(source())

    async def send(message: Message) -> None:
        del message

    with pytest.raises(asyncio.CancelledError):
        await response.stream_response(send)

    assert source_started.is_set()
    assert cleanup_finished.is_set()


def test_sse_response_sets_no_buffering_headers() -> None:
    async def empty() -> AsyncIterator[bytes]:
        if False:
            yield b""

    response = create_sse_response(empty())

    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


@pytest.mark.asyncio
async def test_delayed_response_marks_response_start_send_failure_uncertain() -> None:
    marked = False

    async def source() -> AsyncIterator[bytes]:
        yield b"first"

    async def send(message: object) -> None:
        del message
        raise ConnectionError("start outcome unknown")

    def mark_uncertain() -> None:
        nonlocal marked
        marked = True

    response = create_delayed_sse_response(
        source(),
        on_start_uncertain=mark_uncertain,
    )

    with pytest.raises(ConnectionError, match="outcome unknown"):
        await response.stream_response(send)

    assert marked is True


@pytest.mark.asyncio
async def test_idle_timeout_is_per_item_not_total_duration() -> None:
    async def source() -> AsyncIterator[int]:
        yield 1
        await anyio.sleep(0.01)
        yield 2

    assert [item async for item in with_idle_timeout(source(), 0.1)] == [1, 2]


@pytest.mark.asyncio
async def test_idle_timeout_raises_when_next_item_stalls() -> None:
    async def stalled() -> AsyncIterator[int]:
        await anyio.sleep(1)
        yield 1

    with pytest.raises(StreamIdleTimeoutError):
        _ = [item async for item in with_idle_timeout(stalled(), 0.01)]


def test_resolve_stream_idle_prefers_model_override() -> None:
    settings = TimeoutConfig(
        stream_idle=300,
        stream_idle_overrides={"gpt-5.5": 600, "claude-test": 120},
    )

    assert resolve_stream_idle("claude-test-v2", settings) == 120
    assert resolve_stream_idle("other", settings) == 300
