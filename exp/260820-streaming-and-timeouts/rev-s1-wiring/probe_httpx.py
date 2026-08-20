"""Probe C: what does closing httpx's own `aiter_bytes()` generator actually release?

No project code involved. This asks the library the question directly, because probe B showed
that closing every project-owned hop still leaves `Response.is_closed` False.
"""

import asyncio
import gc
import socket
import time
from typing import Any

import httpx
import uvicorn


async def upstream_app(scope: Any, receive: Any, send: Any) -> None:
    if scope["type"] != "http":
        return
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/event-stream")]})
    for _ in range(4):
        await send({"type": "http.response.body", "body": b": chunk\n\n", "more_body": True})
        await asyncio.sleep(0.01)
    await asyncio.sleep(300)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def pool_state(client: httpx.AsyncClient) -> str:
    pool = client._transport._pool  # type: ignore[attr-defined]
    return f"{len(pool.connections)} conn(s): " + ", ".join(str(c) for c in pool.connections)


async def variant(port: int, label: str, closer: str) -> None:
    client = httpx.AsyncClient(timeout=None)
    request = client.build_request("POST", f"http://127.0.0.1:{port}/x", json={})
    response = await client.send(request, stream=True)
    agen = response.aiter_bytes()
    await anext(agen)

    if closer == "aiter_bytes.aclose":
        await agen.aclose()
    elif closer == "response.aclose":
        await response.aclose()
    elif closer == "aiter_bytes.aclose+gc":
        await agen.aclose()
        gc.collect()
        await asyncio.sleep(0.1)
        gc.collect()
        await asyncio.sleep(0.1)

    print(f"  {label:<34} is_closed={str(response.is_closed):<5} pool={pool_state(client)}", flush=True)
    await client.aclose()


async def main() -> None:
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(upstream_app, host="127.0.0.1", port=port, log_level="error"))
    asyncio.create_task(server.serve())
    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.02)

    print(f"httpx {httpx.__version__}", flush=True)
    await variant(port, "aiter_bytes().aclose()", "aiter_bytes.aclose")
    await variant(port, "aiter_bytes().aclose() + gc", "aiter_bytes.aclose+gc")
    await variant(port, "response.aclose()", "response.aclose")
    await variant(port, "nothing (control)", "none")

    import os
    import sys

    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    asyncio.run(main())
