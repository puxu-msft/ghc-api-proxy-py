"""Probe: does httpx's read timeout act as a per-read idle timeout during SSE body iteration?

Serves: headers, then a chunk every 0.2s for 5 chunks, then stalls forever.
Client read timeout is 0.5s. If the timeout is per-read, the 5 chunks all arrive
(total 1.0s > 0.5s) and the failure comes ~0.5s after the last chunk.
"""

import asyncio
import time

import httpx


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while True:
        line = await reader.readline()
        if line in (b"\r\n", b"\n", b""):
            break
    writer.write(
        b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
        b"Transfer-Encoding: chunked\r\n\r\n"
    )
    await writer.drain()
    for index in range(5):
        await asyncio.sleep(0.2)
        payload = f"data: {index}\n\n".encode()
        writer.write(f"{len(payload):x}\r\n".encode() + payload + b"\r\n")
        await writer.drain()
    await asyncio.sleep(3600)


async def main() -> None:
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=0.5, write=5.0, pool=5.0)) as client:
            started = time.monotonic()
            request = client.build_request("POST", f"http://127.0.0.1:{port}/x", json={})
            response = await client.send(request, stream=True)
            print(f"headers at {time.monotonic() - started:.2f}s status={response.status_code}")
            last = time.monotonic()
            try:
                async for chunk in response.aiter_bytes():
                    now = time.monotonic()
                    print(f"chunk {chunk!r} at t={now - started:.2f}s gap={now - last:.2f}s")
                    last = now
            except Exception as error:  # noqa: BLE001 - the probe reports whatever it gets
                now = time.monotonic()
                print(f"RAISED {type(error).__module__}.{type(error).__name__}: {error}")
                print(f"  at t={now - started:.2f}s, {now - last:.2f}s after the last chunk")
            await response.aclose()


asyncio.run(main())
