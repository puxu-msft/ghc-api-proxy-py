import asyncio
import sys
from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Callable,
    Generator,
    Mapping,
)
from contextlib import contextmanager
from functools import partial
from typing import Any, cast

import anyio
from fastapi.responses import StreamingResponse
from starlette.requests import ClientDisconnect
from starlette.types import Receive, Scope, Send

from app.errors import ApiError
from app.streaming.keepalive import finish_stream_cleanup
from app.wire_json import dumps

type StreamingChunk = str | bytes | memoryview[Any]


@contextmanager
def collapse_excgroups() -> Generator[None]:
    """Unwrap single-exception groups so a caller sees the error it would raise alone.

    A task group wrapping one child turns `ClientDisconnect` into a group holding it, and every `except ClientDisconnect` upstack stops matching.
    Starlette shipped this as the private `starlette._utils.collapse_excgroups` until 1.0 replaced it with a task-group-shaped helper; importing the private name broke every fresh install that resolved starlette 1.x, so the four lines live here instead.
    """
    try:
        yield
    except BaseException as raised:
        error: BaseException = raised
        while isinstance(error, BaseExceptionGroup):
            group = cast(BaseExceptionGroup[BaseException], error)
            if len(group.exceptions) != 1:
                break
            error = group.exceptions[0]
        if error is raised:
            raise
        context = None if error.__suppress_context__ else error.__context__
        raise error from error.__cause__ or context


def format_sse_event(data: str, *, event: str | None = None) -> bytes:
    lines: list[str] = []
    if event is not None:
        lines.append(f"event: {event}")
    lines.extend(f"data: {line}" for line in data.split("\n"))
    return ("\n".join(lines) + "\n\n").encode()


async def passthrough_bytes(
    stream: AsyncIterator[bytes],
    *,
    cleanup: Callable[[], Awaitable[None]] | None = None,
) -> AsyncGenerator[bytes]:
    try:
        async for chunk in stream:
            if chunk:
                yield chunk
    finally:
        close = getattr(stream, "aclose", None)
        if close is not None:
            await close()
        if cleanup is not None:
            await cleanup()


def create_sse_response(
    stream: AsyncIterator[bytes],
    *,
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
) -> StreamingResponse:
    response_headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    if headers:
        response_headers.update(headers)
    return StreamingResponse(
        stream,
        status_code=status_code,
        headers=response_headers,
        media_type="text/event-stream",
    )


class DelayedStartStreamingResponse(StreamingResponse):
    """Prefetch the first body batch while Starlette still listens for disconnects."""

    on_start_accepted: Callable[[], None] | None = None
    on_start_uncertain: Callable[[], None] | None = None
    on_body_uncertain: Callable[[bytes], Awaitable[None]] | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def stream() -> None:
            try:
                await self.stream_response(send)
            except OSError as error:
                raise ClientDisconnect() from error

        with collapse_excgroups():
            async with anyio.create_task_group() as task_group:

                async def run_until_complete(
                    operation: Callable[[], Awaitable[None]],
                ) -> None:
                    await operation()
                    task_group.cancel_scope.cancel()

                task_group.start_soon(run_until_complete, stream)
                await run_until_complete(partial(self.listen_for_disconnect, receive))

        if self.background is not None:
            await self.background()

    async def stream_response(self, send: Send) -> None:
        body_iterator = self.body_iterator.__aiter__()
        pending: asyncio.Task[StreamingChunk] | None = None

        async def pull_chunk() -> StreamingChunk:
            return await anext(body_iterator)

        async def next_chunk() -> StreamingChunk:
            nonlocal pending
            pending = asyncio.create_task(pull_chunk())
            try:
                chunk = await asyncio.shield(pending)
            except asyncio.CancelledError:
                raise
            except BaseException:
                pending = None
                raise
            pending = None
            return chunk

        try:
            try:
                first = await next_chunk()
            except StopAsyncIteration:
                first = b""
            except ApiError as error:
                detail: dict[str, Any] = {
                    "type": error.wire_type,
                    "message": error.message,
                }
                if error.code is not None:
                    detail["code"] = error.code
                if error.request_id is not None:
                    detail["request_id"] = error.request_id
                body = dumps({"type": "error", "error": detail})
                headers = [(b"content-type", b"application/json")]
                await send(
                    {
                        "type": "http.response.start",
                        "status": error.status_code,
                        "headers": headers,
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return

            try:
                await send(
                    {
                        "type": "http.response.start",
                        "status": self.status_code,
                        "headers": self.raw_headers,
                    }
                )
            except BaseException:
                if self.on_start_uncertain is not None:
                    self.on_start_uncertain()
                raise
            if self.on_start_accepted is not None:
                self.on_start_accepted()
            if first:
                first_bytes = (
                    bytes(first)
                    if isinstance(first, bytes | memoryview)
                    else first.encode(self.charset)
                )
                try:
                    await send(
                        {
                            "type": "http.response.body",
                            "body": first_bytes,
                            "more_body": True,
                        }
                    )
                except BaseException:
                    if self.on_body_uncertain is not None:
                        await self.on_body_uncertain(first_bytes)
                    raise
            while True:
                try:
                    chunk = await next_chunk()
                except StopAsyncIteration:
                    break
                if not isinstance(chunk, bytes | memoryview):
                    chunk = chunk.encode(self.charset)
                try:
                    await send(
                        {"type": "http.response.body", "body": chunk, "more_body": True}
                    )
                except BaseException:
                    if self.on_body_uncertain is not None:
                        await self.on_body_uncertain(bytes(chunk))
                    raise
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            primary = sys.exception()
            if isinstance(primary, GeneratorExit):
                primary = None
            cleanup_error, cleanup_cancellation = await finish_stream_cleanup(
                pending, body_iterator, primary=primary
            )
            primary = primary or cleanup_cancellation
            if primary is not None:
                if cleanup_error is not None:
                    raise primary from cleanup_error
                if cleanup_cancellation is not None:
                    raise primary
            elif cleanup_error is not None:
                raise cleanup_error


def create_delayed_sse_response(
    stream: AsyncIterator[bytes],
    *,
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
    on_start_accepted: Callable[[], None] | None = None,
    on_start_uncertain: Callable[[], None] | None = None,
    on_body_uncertain: Callable[[bytes], Awaitable[None]] | None = None,
) -> StreamingResponse:
    response_headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    if headers:
        response_headers.update(headers)
    response = DelayedStartStreamingResponse(
        stream,
        status_code=status_code,
        headers=response_headers,
        media_type="text/event-stream",
    )
    response.on_start_accepted = on_start_accepted
    response.on_start_uncertain = on_start_uncertain
    response.on_body_uncertain = on_body_uncertain
    return response
