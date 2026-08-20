"""What actually happens when the guard fires, end to end, under a real ASGI server.

Reuses the repo's own `make_client` to build a real chain, then serves its app with uvicorn instead of TestClient so the client sees the wire rather than the harness.
"""
import asyncio
import logging
import sys
from collections.abc import AsyncIterator

import httpx
import uvicorn

sys.path.insert(0, "/tmp/rev-idle-impl/tests/http")
from test_pipeline_app import make_client, sse_upstream  # type: ignore

from app.observability.logging import setup_logging
from app.server.pipeline_app import CHAIN_STATE_KEY, REQUEST_LOGGER

records: list[logging.LogRecord] = []


class Capture(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        records.append(record)


def quiet_upstream(gap: float, *, before_first_block: bool):
    whole = sse_upstream("first")
    if before_first_block:
        head, tail = b"", whole
    else:
        head, _, rest = whole.partition(b"event: message_delta")
        tail = b"event: message_delta" + rest

    def handler(_: httpx.Request) -> httpx.Response:
        async def body() -> AsyncIterator[bytes]:
            if head:
                yield head
            await asyncio.sleep(gap)
            yield tail

        return httpx.Response(200, content=body(), headers={"content-type": "text/event-stream"})

    return handler


async def probe(label: str, before_first_block: bool) -> None:
    records.clear()
    client, _ = make_client(
        quiet_upstream(2.0, before_first_block=before_first_block),
        overrides={"upstream_request_timeouts": {"stream_idle": 1}},
    )
    app = client.app
    chain = app.state._state[CHAIN_STATE_KEY] if hasattr(app.state, "_state") else getattr(app.state, CHAIN_STATE_KEY)

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="critical", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]

    print(f"===== {label} =====")
    body = b""
    err = None
    status = None
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            async with c.stream(
                "POST", f"http://127.0.0.1:{port}/v1/messages",
                json={"model": "claude-model", "messages": [], "stream": True},
            ) as r:
                status = r.status_code
                try:
                    async for chunk in r.aiter_bytes():
                        body += chunk
                except Exception as exc:
                    err = repr(exc)
    except Exception as exc:
        err = repr(exc)

    print(f"  HTTP status seen by client : {status}")
    print(f"  body bytes received        : {len(body)}  {body[:120]!r}...")
    print(f"  body read error            : {err}")
    await asyncio.sleep(0.3)
    lines = [
        (r.msg.get("prefix"), r.msg.get("status"), r.msg.get("event"))
        for r in records
        if r.name == REQUEST_LOGGER and r.levelno >= logging.INFO and isinstance(r.msg, dict)
    ]
    print(f"  completion log lines       : {lines}")
    print(f"  footer entries left behind : {list(chain.active_requests.snapshot()) if hasattr(chain.active_requests,'snapshot') else chain.active_requests}")
    server.should_exit = True
    await task
    print()


async def main() -> None:
    setup_logging()
    logging.getLogger(REQUEST_LOGGER).addHandler(Capture())
    logging.getLogger(REQUEST_LOGGER).setLevel(logging.DEBUG)
    await probe("fired AFTER the first block was committed", before_first_block=False)
    await probe("fired BEFORE any block was committed", before_first_block=True)


asyncio.run(main())
