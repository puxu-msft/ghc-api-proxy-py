"""Repro 2: a pooled connection that sends a request *during* a long drain parks forever.

Shape of the production incident:
  - connection A is running a long request (a streamed model reply);
  - connection B is an idle pooled connection the client keeps;
  - SIGTERM starts the drain: `stop_accepting()` closes the listener AND clears the admission gate;
  - the client sends another request on B; it parks in `gated_app` on `admission_open.wait()` forever;
  - `wait_drained()` waits on `server_state.tasks`, which now never empties.
"""

from __future__ import annotations

import asyncio
import signal
import socket

from fastapi import FastAPI
from uvicorn import Config

from app.lifecycle.activation import ActivatedSocketSet, ExpectedListener
from app.lifecycle.adapter import UvicornListenerAdapter
from app.lifecycle.standalone import StandaloneServer


def _app() -> FastAPI:
    app = FastAPI()

    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    async def slow() -> dict[str, str]:
        await asyncio.sleep(1.5)
        return {"status": "slow-done"}

    app.add_api_route("/health/liveness", liveness)
    app.add_api_route("/slow", slow)
    return app


async def _keep_alive(port: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(b"GET /health/liveness HTTP/1.1\r\nHost: t\r\n\r\n")
    await writer.drain()
    await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)
    await asyncio.wait_for(reader.readexactly(15), 3)
    return reader, writer


async def main() -> int:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(32)
    port = listener.getsockname()[1]
    activated = ActivatedSocketSet(
        {"http-v4": listener},
        [ExpectedListener("http-v4", socket.AF_INET, "127.0.0.1", port)],
    )
    adapter = UvicornListenerAdapter(Config(_app(), log_config=None), activated)
    server = StandaloneServer(adapter, cleanup_timeout=5)
    serve_task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.3)

    # Connection B: pooled, idle, already answered one request.
    b_reader, b_writer = await _keep_alive(port)
    # Connection A: a long request in flight when the signal arrives.
    a_reader, a_writer = await asyncio.open_connection("127.0.0.1", port)
    a_writer.write(b"GET /slow HTTP/1.1\r\nHost: t\r\n\r\n")
    await a_writer.drain()
    await asyncio.sleep(0.2)
    print(f"[repro] connections={adapter.connection_count()} before signal", flush=True)

    print("[repro] SIGTERM -> rung 1 (drain, unbounded by design)", flush=True)
    server.receive_signal(signal.SIGTERM)
    await asyncio.sleep(0.2)

    print("[repro] pooled client sends a request on connection B mid-drain", flush=True)
    b_writer.write(b"GET /health/liveness HTTP/1.1\r\nHost: t\r\n\r\n")
    await b_writer.drain()

    try:
        report = await asyncio.wait_for(asyncio.shield(serve_task), 6)
    except TimeoutError:
        print("[repro] RESULT: HUNG — serve() still waiting 6s after the drain began", flush=True)
        print(f"[repro] connections={adapter.connection_count()}", flush=True)
        serve_task.cancel()
        await asyncio.gather(serve_task, return_exceptions=True)
        return 1
    print(f"[repro] RESULT: exited — {report}", flush=True)

    # The rung-1 promise: the request that was already in flight must have been waited out, not cut.
    a_head = await asyncio.wait_for(a_reader.readuntil(b"\r\n\r\n"), 2)
    a_body = await a_reader.read()
    print(f"[repro] in-flight request A: {a_head.splitlines()[0]!r} body={a_body!r}", flush=True)
    slow_ok = b"200 OK" in a_head and b"slow-done" in a_body

    # The request the pooled client sent mid-drain: answered and disconnected, never left hanging.
    b_tail = await asyncio.wait_for(b_reader.read(), 2)
    print(f"[repro] mid-drain request B got: {b_tail[:80]!r}", flush=True)
    b_closed = b_reader.at_eof()

    for writer in (a_writer, b_writer):
        writer.close()
    print(f"[repro] slow request completed={slow_ok} connection B closed={b_closed}", flush=True)
    return 0 if slow_ok and b_closed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
