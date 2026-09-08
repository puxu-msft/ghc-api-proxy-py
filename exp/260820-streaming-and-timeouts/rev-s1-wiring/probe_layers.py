"""Probe B: with the chain closed from the top, how far down does the close actually reach?

Each variant builds the same production chain with one hop's consumption style changed, then
calls `aclose()` on the outermost generator and reports whether the real httpx response is
closed by the time that call returns.

hop names, outermost first:
    tracked   -> app.server.pipeline_app._tracked_delivery   (bare `async for` today)
    delivery  -> app.pipeline.delivery.stream.stream_delivery (aclosing after the change)
    counted   -> app.server.pipeline_app._counted_upstream   (bare `async for` today)
    httpx     -> Response.aiter_bytes / aiter_raw            (library code)
"""

import asyncio
import gc
import socket
import sys
import time
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing
from typing import Any

import httpx
import uvicorn

from app.observability.active_requests import ActiveRequestRegistry
from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import StreamSettings, stream_delivery
from app.server.pipeline_app import (
    _counted_upstream,
    _StreamAccounting,
    _Trace,
    _tracked_delivery,
)

BLOCK = [
    b'event: message_start\ndata: {"type":"message_start","message":{"id":"m","type":"message","role":"assistant","model":"x","content":[],"usage":{"input_tokens":1,"output_tokens":0}}}\n\n',
    b'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n',
    b'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hello"}}\n\n',
    b'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
]


async def upstream_app(scope: Any, receive: Any, send: Any) -> None:
    if scope["type"] != "http":
        return
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/event-stream")]})
    for frame in BLOCK:
        await send({"type": "http.response.body", "body": frame, "more_body": True})
        await asyncio.sleep(0.01)
    await asyncio.sleep(300)


def pool_state(client: httpx.AsyncClient) -> str:
    pool = client._transport._pool  # type: ignore[attr-defined]
    return f"{len(pool.connections)}:" + ",".join(str(c).split(", ")[-2] for c in pool.connections)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class FakeCapabilities:
    unicode = False
    color = False


class FakeChain:
    def __init__(self) -> None:
        self.active_requests = ActiveRequestRegistry()
        self.capabilities = FakeCapabilities()


async def closing_tracked(chunks: AsyncGenerator[bytes], accounting: _StreamAccounting) -> AsyncGenerator[bytes]:
    """`_tracked_delivery` as it would be if it closed what it consumes."""
    try:
        async with aclosing(chunks) as inner:
            async for chunk in inner:
                yield chunk
    finally:
        accounting.finish()


async def closing_counted(chunks: AsyncIterator[bytes], chain: Any, request_id: str, trace: _Trace) -> AsyncGenerator[bytes]:
    """`_counted_upstream` as it would be if it closed what it consumes."""
    close = getattr(chunks, "aclose", None)
    try:
        async for chunk in chunks:
            trace.received += len(chunk)
            chain.active_requests.add_bytes(request_id, len(chunk))
            yield chunk
    finally:
        if close is not None:
            await close()


async def run_variant(port: int, name: str, *, tracked_closes: bool, counted_closes: bool) -> None:
    client = httpx.AsyncClient(timeout=None)
    request = client.build_request("POST", f"http://127.0.0.1:{port}/v1/messages", json={"x": 1})
    response = await client.send(request, stream=True)

    chain = FakeChain()
    trace = _Trace(method="POST", path="/v1/messages", request_id="rid", started=time.monotonic())
    chain.active_requests.add("rid")
    assembler = AnthropicAssembler()
    accounting = _StreamAccounting(chain=chain, request_id="rid", trace=trace, status_code=200, context=None, assembler=assembler)

    counted_factory = closing_counted if counted_closes else _counted_upstream
    tracked_factory = closing_tracked if tracked_closes else _tracked_delivery

    body = tracked_factory(
        stream_delivery(
            counted_factory(response.aiter_bytes(), chain, "rid", trace),
            assembler,
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=15),
            message_id="m",
            model="x",
        ),
        accounting,
    )

    # Pull one block, then walk away and close from the top.
    async for _ in body:
        break
    closed_before = response.is_closed
    await body.aclose()
    closed_after_aclose = response.is_closed
    pool_after = pool_state(client)

    ticks = None
    for tick in range(1, 21):
        await asyncio.sleep(0)
        if response.is_closed:
            ticks = tick
            break
    pool_at_aclose = pool_after
    pool_after_ticks = pool_state(client)
    gc.collect()
    await asyncio.sleep(0.15)
    gc.collect()
    await asyncio.sleep(0.15)
    print(
        f"  {name:<46} is_closed={str(closed_after_aclose):<5} "
        f"pool@aclose={pool_at_aclose:<10} pool@ticks={pool_after_ticks:<10} pool@gc={pool_state(client)}  (before={closed_before})",
        flush=True,
    )
    await client.aclose()


async def main() -> None:
    port = free_port()
    config = uvicorn.Config(upstream_app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    asyncio.create_task(server.serve())
    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.02)

    import app.pipeline.delivery.stream as m

    print(f"stream.py under test: {m.__file__}", flush=True)
    print("aclose() called on the outermost generator; does it reach the httpx response?", flush=True)
    await run_variant(port, "as-shipped (tracked bare, counted bare)", tracked_closes=False, counted_closes=False)
    await run_variant(port, "+ tracked closes delivery", tracked_closes=True, counted_closes=False)
    await run_variant(port, "+ tracked closes, counted closes aiter_bytes", tracked_closes=True, counted_closes=True)
    sys.stdout.flush()
    import os

    os._exit(0)


if __name__ == "__main__":
    asyncio.run(main())
