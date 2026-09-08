"""Is change 3 load-bearing on the NEW chain, measured on a real socket?

Composition is production's, verbatim:
    stream_delivery( _counted_upstream( with_idle_timeout( response.aiter_bytes() ) ) )

The client pulls one delivered block and then closes the delivery generator — a client that went
away with no pull in flight. The question is whether the upstream socket is released there and
then, or left for the collector.
"""

import asyncio
import contextlib

import httpx

from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import StreamSettings, stream_delivery
from app.server.pipeline_app import _counted_upstream  # pyright: ignore[reportPrivateUsage]
from app.streaming.idle_timeout import with_idle_timeout

BLOCK = (
    b'event: message_start\ndata: {"message":{"id":"msg_1","usage":{}}}\n\n'
    b'event: content_block_start\ndata: {"index":0,"content_block":{"type":"text","text":""}}\n\n'
    b'event: content_block_delta\ndata: {"index":0,"delta":{"type":"text_delta","text":"hi"}}\n\n'
    b'event: content_block_stop\ndata: {"index":0}\n\n'
)


class _Chain:
    class _Active:
        def add_bytes(self, request_id: str, count: int) -> None: ...

    active_requests = _Active()


class _Trace:
    received = 0


async def main() -> None:
    events: list[str] = []
    handlers: list[asyncio.Task[None]] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n")
            writer.write(f"{len(BLOCK):x}\r\n".encode() + BLOCK + b"\r\n")
            await writer.drain()
            while await reader.read(1024):
                pass
            events.append("peer closed")
        except (ConnectionResetError, BrokenPipeError):
            events.append("peer reset")
        finally:
            writer.close()

    server = await asyncio.start_server(
        lambda r, w: handlers.append(asyncio.create_task(handle(r, w))), "127.0.0.1", 0
    )
    port = server.sockets[0].getsockname()[1]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5, read=None, write=5, pool=5)) as client:
            request = client.build_request("POST", f"http://127.0.0.1:{port}/v1/messages", json={})
            response = await client.send(request, stream=True)
            delivery = stream_delivery(
                _counted_upstream(
                    with_idle_timeout(response.aiter_bytes(), timeout_seconds=30),
                    _Chain(),  # pyright: ignore[reportArgumentType]
                    "req_1",
                    _Trace(),  # pyright: ignore[reportArgumentType]
                ),
                AnthropicAssembler(),
                buffer=BlockBuffer(policy="block"),
                settings=StreamSettings(sse_ping_interval=0),
                message_id="msg_1",
                model="claude-model",
            )
            assert await anext(delivery), "one block should have been delivered"
            await delivery.aclose()
            # No sleep: this is the question. Was it released by the close, or does it need the collector?
            immediate = (list(events), response.is_closed)
            await asyncio.sleep(0.3)
            print(f"  right after aclose(): server={immediate[0] or ['nothing']}, response.is_closed={immediate[1]}")
            print(f"  after 0.3s of loop:   server={events or ['nothing']}, response.is_closed={response.is_closed}")
    finally:
        server.close()
        for task in handlers:
            task.cancel()
            with contextlib.suppress(BaseException):
                await task


asyncio.run(main())
