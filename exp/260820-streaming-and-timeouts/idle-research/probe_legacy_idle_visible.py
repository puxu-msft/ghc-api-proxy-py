"""Probe: what a client sees when StreamIdleTimeoutError escapes each of the two legacy SSE responses.

Runs a real uvicorn on an ephemeral loopback port so the answer is uvicorn's, not a test client's.

Two routes, both raising the same error the legacy chain raises:
  /plain-before   create_sse_response,          error before any chunk
  /plain-after    create_sse_response,          error after one chunk
  /delayed-before create_delayed_sse_response,  error before any chunk
  /delayed-after  create_delayed_sse_response,  error after one chunk
"""

import asyncio
import socket
import sys
from collections.abc import AsyncGenerator

import httpx
import uvicorn
from fastapi import FastAPI

sys.path.insert(0, "/home/xp/src/ghc-api-proxy-py/src")

from app.streaming.idle_timeout import StreamIdleTimeoutError  # noqa: E402
from app.streaming.sse import create_delayed_sse_response, create_sse_response  # noqa: E402


async def _fail_before() -> AsyncGenerator[bytes]:
    raise StreamIdleTimeoutError("No stream item received for 0.01s")
    yield b""  # pragma: no cover - unreachable, keeps this a generator


async def _fail_after() -> AsyncGenerator[bytes]:
    yield b"event: message_start\ndata: {}\n\n"
    await asyncio.sleep(0.05)
    raise StreamIdleTimeoutError("No stream item received for 0.01s")


app = FastAPI()
app.add_api_route("/plain-before", lambda: create_sse_response(_fail_before()), methods=["GET"])
app.add_api_route("/plain-after", lambda: create_sse_response(_fail_after()), methods=["GET"])
app.add_api_route("/delayed-before", lambda: create_delayed_sse_response(_fail_before()), methods=["GET"])
app.add_api_route("/delayed-after", lambda: create_delayed_sse_response(_fail_after()), methods=["GET"])


async def main() -> None:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    async with httpx.AsyncClient(timeout=10.0) as client:
        for path in ("/plain-before", "/plain-after", "/delayed-before", "/delayed-after"):
            print(f"=== {path}")
            try:
                async with client.stream("GET", f"http://127.0.0.1:{port}{path}") as response:
                    print(f"  status={response.status_code} content-type={response.headers.get('content-type')!r}")
                    body = b""
                    try:
                        async for chunk in response.aiter_bytes():
                            body += chunk
                    except Exception as error:  # noqa: BLE001 - report whatever the client gets
                        print(f"  body read raised {type(error).__module__}.{type(error).__name__}: {error}")
                    print(f"  body={body!r}")
            except Exception as error:  # noqa: BLE001 - report whatever the client gets
                print(f"  request raised {type(error).__module__}.{type(error).__name__}: {error}")
    server.should_exit = True
    await task


asyncio.run(main())
