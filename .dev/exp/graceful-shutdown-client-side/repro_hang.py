"""Repro: graceful shutdown never returns when a pooled client sends a request after stop_accepting."""

from __future__ import annotations

import asyncio
import signal
import socket
import sys

from fastapi import FastAPI
from uvicorn import Config

from app.lifecycle.activation import ActivatedSocketSet, ExpectedListener
from app.lifecycle.adapter import UvicornListenerAdapter
from app.lifecycle.standalone import StandaloneServer


def _app() -> FastAPI:
    app = FastAPI()

    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    app.add_api_route("/health/liveness", liveness)
    return app


async def main(scenario: str) -> int:
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

    # A pooled client: one connection, kept alive across requests.
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(b"GET /health/liveness HTTP/1.1\r\nHost: t\r\n\r\n")
    await writer.drain()
    head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)
    body = await asyncio.wait_for(reader.readexactly(15), 3)
    print(f"[repro] first request answered: {head.splitlines()[0]!r} {body!r}", flush=True)
    print(f"[repro] headers: {head!r}", flush=True)
    print(f"[repro] connections before signal: {adapter.connection_count()}", flush=True)

    print("[repro] sending SIGTERM-equivalent (rung 1: drain)", flush=True)
    server.receive_signal(signal.SIGTERM)
    await asyncio.sleep(0.2)
    print(f"[repro] connections still open: {adapter.connection_count()}", flush=True)

    if scenario == "second-request":
        print("[repro] pooled client sends a second request on the same connection", flush=True)
        writer.write(b"GET /health/liveness HTTP/1.1\r\nHost: t\r\n\r\n")
        await writer.drain()

    try:
        report = await asyncio.wait_for(asyncio.shield(serve_task), 4)
    except TimeoutError:
        print("[repro] RESULT: HUNG — serve() did not return within 4s", flush=True)
        print(f"[repro] connections={adapter.connection_count()}", flush=True)
        serve_task.cancel()
        writer.close()
        return 1
    print(f"[repro] RESULT: exited cleanly — {report}", flush=True)
    writer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "second-request")))
