"""Does httpx's `read` timeout bound *total* time-to-headers, or only the gap between reads?

The user's config text says `response_header` is "从请求发起到开始收到 HTTP 响应头的最大秒数"
— a total. httpx's read timeout is documented per read operation. This measures which.

Scenario: read timeout 1.0s. Server dribbles the response headers one line per 0.7s,
taking 3.5s in total before the blank line. If the guard is a total, it fires at ~1.0s.
If it is an inter-read gap, it never fires and the headers arrive at ~3.5s.
"""

import asyncio
import sys
import time

import httpx
from anthropic import AsyncAnthropic

sys.path.insert(0, "/home/xp/src/ghc-api-proxy-py/src")

T0 = time.monotonic()


def log(msg: str) -> None:
    print(f"[{time.monotonic() - T0:7.3f}s] {msg}", flush=True)


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        head = await reader.readuntil(b"\r\n\r\n")
        length = 0
        for raw in head.decode("latin-1").split("\r\n"):
            if raw.lower().startswith("content-length:"):
                length = int(raw.split(":", 1)[1].strip())
        if length:
            await reader.readexactly(length)
        log("server: request received; dribbling header lines 0.7s apart")
        for piece in (
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: text/event-stream\r\n",
            b"X-Filler-1: a\r\n",
            b"X-Filler-2: b\r\n",
            b"Transfer-Encoding: chunked\r\n",
            b"\r\n",
        ):
            await asyncio.sleep(0.7)
            writer.write(piece)
            await writer.drain()
            log(f"server: wrote {piece!r}")
        writer.write(b"5\r\nhello\r\n0\r\n\r\n")
        await writer.drain()
        log("server: body complete")
    except Exception as e:  # noqa: BLE001
        log(f"server: {type(e).__name__}")
    finally:
        writer.close()


async def main() -> None:
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    http_client = httpx.AsyncClient(limits=httpx.Limits(keepalive_expiry=15.0))
    sdk = AsyncAnthropic(
        api_key="k", base_url=f"http://127.0.0.1:{port}", http_client=http_client, max_retries=0
    )
    log("client: send with per-request timeout read=1.0s")
    try:
        resp = await sdk.post(
            "/v1/messages",
            cast_to=httpx.Response,
            body={"model": "probe"},
            options={"headers": {"x": "1"}, "timeout": httpx.Timeout(1.0, connect=5.0)},
            stream=True,
        )
        log(f"client: AWAIT RETURNED status={resp.status_code} (read timeout never fired)")
        await resp.aclose()
    except BaseException as e:  # noqa: BLE001
        log(f"client: RAISED {type(e).__name__}: {e}")
    await http_client.aclose()
    server.close()
    await server.wait_closed()


asyncio.run(main())
