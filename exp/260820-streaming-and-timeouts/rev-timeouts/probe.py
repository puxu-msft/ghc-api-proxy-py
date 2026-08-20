"""Real local HTTP server + the production send call, to measure when `await send` returns.

Replicates GhcApiClient._post_anthropic exactly:
    await AsyncAnthropic(...).post(path, cast_to=httpx.Response, body=..., options={...}, stream=...)
and the production httpx client shape from app.server.composition.build_http_client
(no timeout= argument, so httpx defaults, so the SDK falls back to its own DEFAULT_TIMEOUT).
"""

import asyncio
import sys
import time
from dataclasses import dataclass, field
from typing import Any, cast

import httpx
from anthropic import AsyncAnthropic
from anthropic._types import Body as AnthropicBody

sys.path.insert(0, "/home/xp/src/ghc-api-proxy-py/src")
from app.ghc_client.errors import normalize_upstream_error  # noqa: E402
from app.pipeline.exceptions import classify  # noqa: E402

T0 = time.monotonic()


def ts() -> float:
    return time.monotonic() - T0


LOG: list[str] = []


def log(msg: str) -> None:
    line = f"[{ts():7.3f}s] {msg}"
    LOG.append(line)
    print(line, flush=True)


@dataclass
class ServerPlan:
    header_delay: float = 0.0
    first_chunk_delay: float = 0.0
    chunk_gap: float = 0.0
    chunks: int = 3
    never_end: bool = False
    events: list[str] = field(default_factory=list)


async def start_server(plan: ServerPlan) -> tuple[asyncio.AbstractServer, int]:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            length = 0
            for raw in head.decode("latin-1").split("\r\n"):
                if raw.lower().startswith("content-length:"):
                    length = int(raw.split(":", 1)[1].strip())
            if length:
                await reader.readexactly(length)
            log("server: request fully received")
            await asyncio.sleep(plan.header_delay)
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/event-stream\r\n"
                b"Transfer-Encoding: chunked\r\n"
                b"\r\n"
            )
            await writer.drain()
            log("server: HEADERS SENT")
            await asyncio.sleep(plan.first_chunk_delay)
            for i in range(plan.chunks):
                if i:
                    await asyncio.sleep(plan.chunk_gap)
                payload = f"data: chunk-{i}\n\n".encode()
                writer.write(f"{len(payload):X}\r\n".encode() + payload + b"\r\n")
                await writer.drain()
                log(f"server: body chunk {i} sent")
            if plan.never_end:
                log("server: holding connection open forever")
                await asyncio.sleep(3600)
            writer.write(b"0\r\n\r\n")
            await writer.drain()
            log("server: BODY COMPLETE")
        except (asyncio.IncompleteReadError, ConnectionResetError, asyncio.CancelledError) as e:
            log(f"server: client went away ({type(e).__name__})")
        finally:
            try:
                writer.close()
            except Exception:
                pass

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port


def make_client(port: int, *, timeout: Any = None) -> tuple[httpx.AsyncClient, AsyncAnthropic]:
    # Exactly app.server.composition.build_http_client: no timeout= argument.
    http_client = httpx.AsyncClient(limits=httpx.Limits(keepalive_expiry=15.0))
    kwargs: dict[str, Any] = {}
    if timeout is not None:
        kwargs["timeout"] = timeout
    sdk = AsyncAnthropic(
        api_key="proxy-managed",
        base_url=f"http://127.0.0.1:{port}",
        http_client=http_client,
        max_retries=0,
        **kwargs,
    )
    return http_client, sdk


async def send(sdk: AsyncAnthropic, *, stream: bool, options: dict[str, Any] | None = None) -> httpx.Response:
    opts: dict[str, Any] = {"headers": {"x-probe": "1"}}
    if options:
        opts.update(options)
    return await sdk.post(
        "/v1/messages",
        cast_to=httpx.Response,
        body=cast(AnthropicBody, {"model": "probe", "messages": []}),
        options=opts,
        stream=stream,
    )


async def scenario(name: str, plan: ServerPlan, run: Any) -> None:
    print(f"\n=== {name} ===", flush=True)
    server, port = await start_server(plan)
    try:
        await run(port)
    finally:
        server.close()
        await server.wait_closed()


# --- Q1: when does `await send` return? -------------------------------------------------------


async def q1_stream_true(port: int) -> None:
    http_client, sdk = make_client(port)
    log("client: about to await send(stream=True)")
    resp = await send(sdk, stream=True)
    log(f"client: AWAIT RETURNED status={resp.status_code} is_closed={resp.is_closed}")
    n = 0
    async for _ in resp.aiter_bytes():
        n += 1
        log(f"client: got body block {n}")
    log("client: body iteration finished")
    await http_client.aclose()


async def q1_stream_false(port: int) -> None:
    http_client, sdk = make_client(port)
    log("client: about to await send(stream=False)")
    resp = await send(sdk, stream=False)
    log(f"client: AWAIT RETURNED status={resp.status_code} bytes={len(resp.content)}")
    await http_client.aclose()


# --- Q2: what does asyncio.timeout around send actually bound? --------------------------------


async def q2(port: int, *, stream: bool, deadline: float) -> None:
    http_client, sdk = make_client(port)
    log(f"client: asyncio.timeout({deadline}) around send(stream={stream})")
    try:
        async with asyncio.timeout(deadline):
            resp = await send(sdk, stream=stream)
        log(f"client: AWAIT RETURNED status={resp.status_code} (deadline did NOT fire)")
        if stream:
            try:
                async for _ in resp.aiter_bytes():
                    log("client: body block (outside the deadline scope)")
            except Exception as e:  # noqa: BLE001
                log(f"client: body raised {type(e).__name__}: {e}")
    except TimeoutError as e:
        log(f"client: DEADLINE FIRED -> {type(e).__name__}: {e!s}")
    await http_client.aclose()


# --- Q3/Q6: per-request timeout via options -----------------------------------------------


async def q3_header_timeout(port: int) -> None:
    http_client, sdk = make_client(port)
    log("client: send(stream=True) with options timeout=1.0s, server delays headers")
    try:
        await send(sdk, stream=True, options={"timeout": httpx.Timeout(1.0, connect=5.0)})
        log("client: AWAIT RETURNED (no timeout!)")
    except BaseException as e:  # noqa: BLE001
        norm = normalize_upstream_error(e)
        log(f"client: RAISED {type(e).__module__}.{type(e).__name__}: {e}")
        log(f"        normalize_upstream_error -> {type(norm).__name__ if norm else None}: {norm}")
        if norm is not None:
            log(f"        classify -> {classify(norm)}")
    await http_client.aclose()


async def q3_body_phase(port: int) -> None:
    http_client, sdk = make_client(port)
    log("client: send(stream=True) options timeout=1.0s, headers fast, body gap 2.0s")
    resp = await send(sdk, stream=True, options={"timeout": httpx.Timeout(1.0, connect=5.0)})
    log(f"client: AWAIT RETURNED status={resp.status_code}")
    try:
        async for _ in resp.aiter_bytes():
            log("client: body block")
    except BaseException as e:  # noqa: BLE001
        norm = normalize_upstream_error(e)
        log(f"client: BODY RAISED {type(e).__module__}.{type(e).__name__}: {e}")
        log(f"        normalize_upstream_error -> {type(norm).__name__ if norm else None}")
    await http_client.aclose()


async def q3_client_level_timeout(port: int) -> None:
    """Same guard but set on the SDK client, not per request."""
    http_client, sdk = make_client(port, timeout=httpx.Timeout(1.0, connect=5.0))
    log(f"client: SDK client-level timeout={sdk.timeout}")
    try:
        await send(sdk, stream=True)
        log("client: AWAIT RETURNED (no timeout!)")
    except BaseException as e:  # noqa: BLE001
        log(f"client: RAISED {type(e).__name__}: {e}")
    await http_client.aclose()


# --- Q5: what is the effective implicit timeout today? ----------------------------------------


async def q5_effective_default(port: int) -> None:
    http_client, sdk = make_client(port)
    log(f"httpx client default timeout = {http_client.timeout}")
    log(f"SDK effective timeout        = {sdk.timeout}")
    from anthropic._constants import DEFAULT_TIMEOUT as ANTHROPIC_DEFAULT

    from openai._constants import DEFAULT_TIMEOUT as OPENAI_DEFAULT

    log(f"anthropic DEFAULT_TIMEOUT    = {ANTHROPIC_DEFAULT}")
    log(f"openai    DEFAULT_TIMEOUT    = {OPENAI_DEFAULT}")
    resp = await send(sdk, stream=True)
    log(f"request extensions timeout   = {resp.request.extensions.get('timeout')}")
    await resp.aclose()
    await http_client.aclose()


async def main() -> None:
    await scenario(
        "Q1a stream=True: headers at +1.0s, first body at +3.0s, 3 chunks 0.5s apart",
        ServerPlan(header_delay=1.0, first_chunk_delay=2.0, chunk_gap=0.5, chunks=3),
        q1_stream_true,
    )
    await scenario(
        "Q1b stream=False: same server timing",
        ServerPlan(header_delay=1.0, first_chunk_delay=2.0, chunk_gap=0.5, chunks=3),
        q1_stream_false,
    )
    await scenario(
        "Q2a stream=True, asyncio.timeout(2.0), headers at +0.5s, body trickles past the deadline",
        ServerPlan(header_delay=0.5, first_chunk_delay=0.5, chunk_gap=1.5, chunks=4),
        lambda p: q2(p, stream=True, deadline=2.0),
    )
    await scenario(
        "Q2b stream=False, asyncio.timeout(2.0), same server",
        ServerPlan(header_delay=0.5, first_chunk_delay=0.5, chunk_gap=1.5, chunks=4),
        lambda p: q2(p, stream=False, deadline=2.0),
    )
    await scenario(
        "Q3a per-request timeout=1.0s, headers delayed 3.0s",
        ServerPlan(header_delay=3.0, chunks=1),
        q3_header_timeout,
    )
    await scenario(
        "Q3b per-request timeout=1.0s, headers immediate, body gap 2.0s",
        ServerPlan(header_delay=0.0, first_chunk_delay=0.1, chunk_gap=2.0, chunks=3),
        q3_body_phase,
    )
    await scenario(
        "Q3c client-level timeout=1.0s, headers delayed 3.0s",
        ServerPlan(header_delay=3.0, chunks=1),
        q3_client_level_timeout,
    )
    await scenario(
        "Q5 effective default timeout with the production client shape",
        ServerPlan(header_delay=0.0, chunks=1),
        q5_effective_default,
    )


if __name__ == "__main__":
    asyncio.run(main())
