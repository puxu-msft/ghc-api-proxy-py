"""One-shot delivery: the leg with no framer.

Chat Completions has no outbound framer — nothing here reads its block boundaries — so its stream is buffered whole and forwarded byte for byte. There is nothing to assemble and nothing to frame, which is exactly why the two things worth pinning are that the bytes come back unchanged, and what happens when they stop coming.
"""

from collections.abc import AsyncIterator

import pytest

from app.pipeline.delivery.stream import one_shot_delivery
from app.streaming.idle_timeout import StreamIdleTimeoutError

CHUNKS = [
    b'data: {"id":"cc-1","choices":[{"delta":{"content":"Hello"}}]}\n\n',
    b'data: {"id":"cc-1","choices":[{"delta":{"content":" world"}}]}\n\n',
    b"data: [DONE]\n\n",
]


async def feed(*chunks: bytes, fail_after: int | None = None) -> AsyncIterator[bytes]:
    for index, chunk in enumerate(chunks):
        if fail_after is not None and index == fail_after:
            raise StreamIdleTimeoutError("upstream went quiet")
        yield chunk


async def collect(source: AsyncIterator[bytes]) -> bytes:
    out = bytearray()
    async for chunk in one_shot_delivery(source):
        out += chunk
    return bytes(out)


@pytest.mark.asyncio
async def test_the_stream_comes_back_byte_for_byte() -> None:
    """Not "the same events" — the same bytes. Nothing here is entitled to reinterpret them."""
    assert await collect(feed(*CHUNKS)) == b"".join(CHUNKS)


@pytest.mark.asyncio
async def test_it_arrives_as_one_write() -> None:
    """The delivery unit is the whole stream, which is the cost of having no block boundaries."""
    completed: list[str] = []
    written = [
        chunk
        async for chunk in one_shot_delivery(
            feed(*CHUNKS), on_complete=lambda: completed.append("complete")
        )
    ]

    assert written == [b"".join(CHUNKS)]
    assert completed == ["complete"]


@pytest.mark.asyncio
async def test_nothing_at_all_produces_nothing_at_all() -> None:
    """An empty write would be a delivery. There was none."""
    assert [chunk async for chunk in one_shot_delivery(feed())] == []


@pytest.mark.asyncio
async def test_a_guard_that_fires_still_hands_over_what_had_arrived() -> None:
    """The bytes upstream already sent go out, and then the failure propagates.

    They are upstream's own and already valid SSE for this dialect, so forwarding them says more than silence and invents nothing. The client is not told *why* it stopped — that would need an error frame in a dialect nothing here can frame — but it can see that it stopped: this dialect ends with `data: [DONE]`, and there is not one.

    Before 2026-08-22 the exception unwound with the buffer still in hand and the client got a 200 with an empty body, which is the same symptom the one-shot path was added to remove.
    """
    delivered = bytearray()
    completed: list[str] = []
    with pytest.raises(StreamIdleTimeoutError):
        async for chunk in one_shot_delivery(
            feed(*CHUNKS, fail_after=2),
            on_complete=lambda: completed.append("complete"),
        ):
            delivered += chunk

    assert bytes(delivered) == b"".join(CHUNKS[:2])
    assert b"[DONE]" not in delivered
    assert completed == [], "a partial body is not the one-shot completion unit"


@pytest.mark.asyncio
async def test_a_guard_that_fires_before_any_byte_hands_over_nothing() -> None:
    """No bytes is not an empty delivery either — the failure is all there is to report."""
    delivered = bytearray()
    with pytest.raises(StreamIdleTimeoutError):
        async for chunk in one_shot_delivery(feed(*CHUNKS, fail_after=0)):
            delivered += chunk

    assert delivered == b""
