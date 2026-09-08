"""The other half: a client that stops reading while upstream still has data buffered.

The pull is NOT in flight at that moment (the delivery loop is suspended at a `yield`), so releasing the upstream depends entirely on the explicit close chain — which is where `_counted_upstream`'s bare `async for` sits.
"""
import asyncio
import gc

import httpx

from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import StreamSettings, stream_delivery
from app.server.pipeline_app import _counted_upstream
from app.streaming.idle_timeout import with_idle_timeout

HEAD = b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n"


def frames(n):
    out = b""
    for i in range(n):
        out += b'event: content_block_start\ndata: {"index":%d,"content_block":{"type":"text"}}\n\n' % i
        out += b'event: content_block_delta\ndata: {"index":%d,"delta":{"type":"text_delta","text":"x"}}\n\n' % i
        out += b'event: content_block_stop\ndata: {"index":%d}\n\n' % i
    return out


state = {}


async def handle(reader, writer):
    await reader.readuntil(b"\r\n\r\n")
    writer.write(HEAD)
    payload = frames(8)                       # many complete blocks in ONE chunk
    writer.write(b"%x\r\n%s\r\n" % (len(payload), payload))
    await writer.drain()
    try:
        await reader.read()
        state["peer_closed"] = True
    finally:
        writer.close()


class FakeActive:
    def add_bytes(self, *a): pass


class FakeChain:
    active_requests = FakeActive()


class FakeTrace:
    received = 0


async def run(use_guard: bool) -> None:
    state.clear()
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with httpx.AsyncClient() as client:
        req = client.build_request("GET", f"http://127.0.0.1:{port}/x")
        response = await client.send(req, stream=True)
        pool = client._transport._pool
        raw = response.aiter_bytes()
        source = with_idle_timeout(raw, timeout_seconds=30) if use_guard else raw
        delivery = stream_delivery(
            _counted_upstream(source, FakeChain(), "r1", FakeTrace()),
            AnthropicAssembler(), buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0), message_id="m", model="model",
        )
        del source, raw                       # nothing but the chain holds them, as in production
        async for _ in delivery:
            break                             # one block out, then the client goes away
        await delivery.aclose()
        label = f"guard={'on ' if use_guard else 'off'}"
        print(f"{label}: pool right after aclose(): {pool.connections}")
        for _ in range(50):
            await asyncio.sleep(0)
        print(f"{label}: pool after 50 ticks     : {pool.connections}")
        gc.collect()
        await asyncio.sleep(0.2)
        print(f"{label}: pool after gc + 0.2s    : {pool.connections}")
        print(f"{label}: server saw peer close   : {state.get('peer_closed', False)}")
    server.close()
    await server.wait_closed()
    print()


async def main():
    await run(use_guard=False)
    await run(use_guard=True)


asyncio.run(main())
