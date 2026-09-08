"""After the new pipeline's idle guard fires, is the upstream HTTP response actually released?

Real socket server, real httpx AsyncClient, production composition copied from
`pipeline_app.py:277-301` (minus footer/logging, which do not touch the socket).
"""
import asyncio
import sys

import httpx

from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import StreamSettings, stream_delivery
from app.streaming.idle_timeout import StreamIdleTimeoutError, with_idle_timeout

HEAD = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/event-stream\r\n"
    b"Transfer-Encoding: chunked\r\n\r\n"
)
FRAMES = [
    b'event: content_block_start\ndata: {"index":0,"content_block":{"type":"text"}}\n\n',
    b'event: content_block_delta\ndata: {"index":0,"delta":{"type":"text_delta","text":"one"}}\n\n',
    b'event: content_block_stop\ndata: {"index":0}\n\n',
]

server_state: dict[str, object] = {}


def chunked(payload: bytes) -> bytes:
    return b"%x\r\n%s\r\n" % (len(payload), payload)


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    await reader.readuntil(b"\r\n\r\n")
    writer.write(HEAD)
    for f in FRAMES:
        writer.write(chunked(f))
    await writer.drain()
    server_state["sent"] = True
    # Now upstream goes quiet forever. Wait for the peer to hang up.
    try:
        data = await reader.read()          # returns b"" on FIN
        server_state["peer_closed_at"] = asyncio.get_running_loop().time()
        server_state["peer_read"] = data
    except Exception as exc:                 # noqa: BLE001 - probe
        server_state["peer_error"] = repr(exc)
    finally:
        writer.close()


async def counted(chunks):
    """`_counted_upstream`, minus the bookkeeping — the bare `async for` is the shape that matters."""
    async for chunk in chunks:
        yield chunk


async def main() -> None:
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    async with httpx.AsyncClient() as client:
        request = client.build_request("GET", f"http://127.0.0.1:{port}/x")
        response = await client.send(request, stream=True)
        pool = client._transport._pool  # noqa: SLF001 - probe
        print("connections after headers:", pool.connections)

        delivery = stream_delivery(
            counted(with_idle_timeout(response.aiter_bytes(), timeout_seconds=1)),
            AnthropicAssembler(),
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0),
            message_id="m",
            model="model",
        )
        raised: BaseException | None = None
        t0 = asyncio.get_running_loop().time()
        try:
            async for _ in delivery:
                pass
        except BaseException as exc:  # noqa: BLE001 - probe
            raised = exc
        t1 = asyncio.get_running_loop().time()

        print(f"raised: {type(raised).__name__}: {raised}")
        print(f"fired after {t1 - t0:.2f}s")
        print("response.is_closed  right after the raise:", response.is_closed)
        print("response.is_stream_consumed:", response.is_stream_consumed)
        print("pool connections     right after the raise:", pool.connections)
        for _ in range(50):
            await asyncio.sleep(0)
        print("response.is_closed  after 50 ticks:", response.is_closed)
        print("pool connections     after 50 ticks:", pool.connections)
        await asyncio.sleep(0.3)
        print("response.is_closed  after 0.3s:", response.is_closed)
        print("pool connections     after 0.3s:", pool.connections)
        print("server saw peer close:", "peer_closed_at" in server_state, server_state.get("peer_read"), server_state.get("peer_error"))

    server.close()
    await server.wait_closed()


asyncio.run(main())
