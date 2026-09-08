"""(d) Change 3 against a real httpx response, in the legacy composition's shape."""

import asyncio
import contextlib

import httpx

from app.streaming.idle_timeout import StreamIdleTimeoutError, with_idle_timeout
from app.streaming.sse import passthrough_bytes

MODE = "stall"


async def scenario(mode: str, idle: float) -> None:
    events: list[str] = []
    handlers: list[asyncio.Task[None]] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        events.append("server: connection open")
        try:
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n")
            payload = b"event: message_start\ndata: {}\n\n"
            writer.write(f"{len(payload):x}\r\n".encode() + payload + b"\r\n")
            if mode == "finish":
                writer.write(b"0\r\n\r\n")
            await writer.drain()
            # Block until the peer goes away, which is what we are trying to observe.
            while await reader.read(1024):
                pass
            events.append("server: peer closed the connection")
        except (ConnectionResetError, BrokenPipeError):
            events.append("server: connection reset by peer")
        finally:
            writer.close()

    def spawn(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        handlers.append(asyncio.create_task(handle(reader, writer)))

    server = await asyncio.start_server(spawn, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    notes: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5, read=None, write=5, pool=5)) as client:
            request = client.build_request("POST", f"http://127.0.0.1:{port}/v1/messages", json={})
            upstream = await client.send(request, stream=True)
            guarded = with_idle_timeout(upstream.aiter_raw(), timeout_seconds=idle)
            stream = passthrough_bytes(guarded, cleanup=upstream.aclose)
            try:
                async with asyncio.timeout(3):
                    async for _ in stream:
                        pass
                notes.append("stream drained normally")
            except StreamIdleTimeoutError as error:
                notes.append(f"guard fired: {error}")
            except TimeoutError:
                notes.append("guard never fired within 3s")
                await stream.aclose()
            except BaseException as error:
                notes.append(f"UNEXPECTED {type(error).__name__}: {error}")
            notes.append(f"response.is_closed={upstream.is_closed}")
            try:
                await upstream.aclose()
                notes.append("a further aclose() is a no-op")
            except BaseException as error:
                notes.append(f"further aclose() RAISED {type(error).__name__}: {error}")
            await asyncio.sleep(0.3)
    finally:
        server.close()
        for task in handlers:
            task.cancel()
            with contextlib.suppress(BaseException):
                await task
    print(f"[{mode}, idle={idle}] " + " | ".join(notes))
    print(f"    server observed: {events}")


async def main() -> None:
    await scenario("stall", 0.5)
    await scenario("finish", 30)
    await scenario("stall", 0)


asyncio.run(main())
