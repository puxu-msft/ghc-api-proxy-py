"""Probe: does a client disconnect close the upstream httpx response, deterministically?

Wires exactly what `app.server.pipeline_app._dispatch` wires for a streaming request:

    _AccountedStreamingResponse(
        _tracked_delivery(
            stream_delivery(
                _counted_upstream(response.aiter_bytes(), ...), ...),
            accounting),
        accounting)

and drives it through the real Starlette `StreamingResponse.__call__` with an ASGI
scope whose `spec_version` is what uvicorn 0.40 sends ("2.3"), so the task-group +
listen_for_disconnect branch is the one taken — the production branch.

The upstream is a real local uvicorn server reached through a real httpx AsyncClient,
so "closed" means the HTTP response object is closed and the pooled connection released.

Run:  PYTHONPATH=<src> .venv/bin/python probe_close_chain.py
"""

import asyncio
import gc
import os
import logging
import socket
import sys
import time
from typing import Any

import httpx
import uvicorn

from app.observability.active_requests import ActiveRequestRegistry
from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import StreamSettings, stream_delivery
from app.server.pipeline_app import (
    _AccountedStreamingResponse,
    _counted_upstream,
    _StreamAccounting,
    _Trace,
    _tracked_delivery,
)

# One complete Anthropic-shaped block, then silence: a model that is still thinking.
BLOCK = [
    b'event: message_start\ndata: {"type":"message_start","message":{"id":"m","type":"message","role":"assistant","model":"x","content":[],"usage":{"input_tokens":1,"output_tokens":0}}}\n\n',
    b'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n',
    b'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hello"}}\n\n',
    b'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
]

upstream_state: dict[str, Any] = {"connections_open": 0, "closed_at": None, "saw_disconnect": None}


async def upstream_app(scope: Any, receive: Any, send: Any) -> None:
    if scope["type"] != "http":
        return
    upstream_state["connections_open"] += 1

    async def watch() -> None:
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                upstream_state["saw_disconnect"] = time.monotonic()
                return

    watcher = asyncio.create_task(watch())
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/event-stream")]})
    try:
        for frame in BLOCK:
            await send({"type": "http.response.body", "body": frame, "more_body": True})
            await asyncio.sleep(0.01)
        if os.environ.get("KEEP_SENDING"):
            # An upstream that goes on talking after the client is gone.
            for _ in range(100):
                await send({"type": "http.response.body", "body": b": late\n\n", "more_body": True})
                await asyncio.sleep(0.01)
        else:
            for _ in range(600):
                if upstream_state["saw_disconnect"] is not None:
                    break
                await asyncio.sleep(0.01)
    finally:
        upstream_state["connections_open"] -= 1
        upstream_state["closed_at"] = time.monotonic()


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


LOG_LINES: list[tuple[float, str]] = []


class Capture(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        LOG_LINES.append((time.monotonic(), record.getMessage()))


async def main() -> None:
    logging.getLogger("app.request").addHandler(Capture())
    logging.getLogger("app.request").setLevel(logging.INFO)

    port = free_port()
    config = uvicorn.Config(upstream_app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    serving = asyncio.create_task(server.serve())
    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.02)

    client = httpx.AsyncClient(timeout=None)
    request = client.build_request("POST", f"http://127.0.0.1:{port}/v1/messages", json={"x": 1})
    print(f"upstream started={server.started} port={port}", flush=True)
    response = await client.send(request, stream=True)
    print("upstream response headers received", flush=True)

    chain = FakeChain()
    trace = _Trace(method="POST", path="/v1/messages", request_id="rid", started=time.monotonic())
    chain.active_requests.add("rid")
    assembler = AnthropicAssembler()
    accounting = _StreamAccounting(
        chain=chain,  # type: ignore[arg-type]
        request_id="rid",
        trace=trace,
        status_code=200,
        context=None,
        assembler=assembler,
    )
    body = _tracked_delivery(
        stream_delivery(
            _counted_upstream(response.aiter_bytes(), chain, "rid", trace),  # type: ignore[arg-type]
            assembler,
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=15),
            message_id="m",
            model="x",
        ),
        accounting,
    )
    if os.environ.get("CLOSE_BODY"):
        # What `DelayedStartStreamingResponse.stream_response` already does on the legacy chain:
        # settle the body iterator in a `finally` outside everything the framework does.
        class ClosingAccountedStreamingResponse(_AccountedStreamingResponse):
            async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
                try:
                    await super().__call__(scope, receive, send)
                finally:
                    close = getattr(self.body_iterator, "aclose", None)
                    if close is not None:
                        await close()

        asgi_response = ClosingAccountedStreamingResponse(body, accounting, status_code=200, media_type="text/event-stream")
    else:
        asgi_response = _AccountedStreamingResponse(body, accounting, status_code=200, media_type="text/event-stream")

    disconnect = asyncio.Event()
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            # The client has seen a block and walks away — this is Esc.
            disconnect.set()
            if os.environ.get("SLOW_SEND"):
                # A client that stopped reading: the cancel then lands inside `send`, with every
                # generator on the chain suspended at a `yield` rather than waiting on upstream.
                await asyncio.sleep(5)

    async def receive() -> dict[str, Any]:
        await disconnect.wait()
        return {"type": "http.disconnect"}

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "method": "POST",
        "path": "/v1/messages",
        "headers": [],
        "http_version": "1.1",
    }

    t0 = time.monotonic()
    print("driving asgi response...", flush=True)
    try:
        await asyncio.wait_for(asgi_response(scope, receive, send), 10)
    except TimeoutError:
        print("!! StreamingResponse.__call__ did not return within 10s", flush=True)
    t_return = time.monotonic()

    print("=== at the moment StreamingResponse.__call__ returned ===")
    print(f"  frames sent downstream        : {len([m for m in sent if m['type'] == 'http.response.body'])}")
    print(f"  accounting.done               : {accounting.done}")
    print(f"  completion log lines          : {len(LOG_LINES)}")
    print(f"  trace.received (bytes)        : {trace.received}")
    print(f"  active_requests               : {[r.request_id for r in chain.active_requests.snapshot()]}")
    print(f"  httpx response.is_closed      : {response.is_closed}")
    print(f"  upstream conns open           : {upstream_state['connections_open']}")

    print(f"  pool                          : {pool_state(client)}")
    logged_received = trace.received
    # In production the routing frame drops the response as soon as the request coroutine
    # returns. Holding it here would keep the whole chain reachable and fake a leak.
    del asgi_response, body
    print("  --- settling after the response object is dropped (only the collector can act) ---")
    for label, action in (("+10 ticks", "ticks"), ("+0.3s", "sleep"), ("+gc.collect()", "gc"), ("+0.3s", "sleep"), ("+gc.collect()", "gc"), ("+1.0s", "long")):
        if action == "ticks":
            for _ in range(10):
                await asyncio.sleep(0)
        elif action == "sleep":
            await asyncio.sleep(0.3)
        elif action == "long":
            await asyncio.sleep(1.0)
        else:
            gc.collect()
            await asyncio.sleep(0)
        live = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and t is not serving]
        seen = "yes" if upstream_state["saw_disconnect"] is not None else "no"
        print(f"    {label:<16} is_closed={str(response.is_closed):<5} pool={pool_state(client):<12} upstream_saw_disconnect={seen} tasks={len(live)}")
    print(f"  trace.received at log time    : {logged_received}")
    print(f"  trace.received 1.6s later     : {trace.received}  (drift={trace.received - logged_received})")
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and t is not serving]
    print(f"  leftover tasks                : {len(pending)}")
    for t in pending:
        print(f"      {t!r}")
    print(f"  wall time in __call__         : {t_return - t0:.3f}s")
    print(f"  log line text                 : {LOG_LINES[0][1][:200] if LOG_LINES else '(none)'}")

    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    print(f"src under test: {sys.path[0] if sys.path[0] else '(cwd)'}")
    import app.pipeline.delivery.stream as m

    print(f"stream.py      : {m.__file__}")
    asyncio.run(main())
