from collections.abc import AsyncIterator, Mapping

from fastapi.responses import StreamingResponse


def format_sse_event(data: str, *, event: str | None = None) -> bytes:
    lines: list[str] = []
    if event is not None:
        lines.append(f"event: {event}")
    lines.extend(f"data: {line}" for line in data.split("\n"))
    return ("\n".join(lines) + "\n\n").encode()


async def passthrough_bytes(stream: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    try:
        async for chunk in stream:
            if chunk:
                yield chunk
    finally:
        close = getattr(stream, "aclose", None)
        if close is not None:
            await close()


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