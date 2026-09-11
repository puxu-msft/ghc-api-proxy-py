"""Does capping streams-per-connection actually shrink a GOAWAY's blast radius on httpx 0.28.1 + httpcore 1.0.9?

Eleven experiments against a local TLS+ALPN h2 server (plus one HTTP/1.1 server) that count their own accepted TCP connections and record which stream landed on which one. Server-side accept counting is the measurement, because it is the only place where "how many TCP connections did this really use" is a fact rather than an inference from client-side private state.

The experiments are ordered so that each one is the control for the next:

1.  `baseline_no_cap`           -- 6 concurrent streams, stock pool. Proves the harness can observe streams sharing one connection at all.
2.  `cap2`                      -- same 6 streams, cap=2. Proves the cap changes the connection count.
3.  `no_cap_goaway`             -- 6 streams on the stock pool, one GOAWAY(NO_ERROR, 2**31-1). Reproduces the production incident locally: all six die.
4.  `cap2_goaway`               -- 6 streams, cap=2, GOAWAY on one of the three connections. The point of the whole exercise: only that connection's streams die.
5.  `cap1`                      -- the value copilot-api-js shipped in b5892380f. One stream per connection.
6.  `cap1_goaway`               -- cap=1 under the same GOAWAY. Exactly one casualty.
7.  `http11_no_h2`              -- the already-shipped alternative, upstream_transport.http2 = false, with one connection killed mid-response. Numerically identical to 5+6.
8.  `server_advertised_mcs`     -- stock pool, server advertises SETTINGS_MAX_CONCURRENT_STREAMS=2. Shows what that knob does instead (throttles, never fans out).
9.  `cap2_plus_advertised_mcs2` -- our cap equal to the server's advertised value. No throttling.
10. `cap4_above_advertised_mcs2`-- our cap above the server's advertised value. The server's number starts to bind.
11. `sharded_clients`           -- 3 separate AsyncClients round-robin. The dumb fallback baseline.

Run: cd /home/xp/src/ghc-api-proxy-py/exp/260820-h2-stream-cap && /home/xp/src/ghc-api-proxy-py/.venv/bin/python run_poc.py
"""

from __future__ import annotations

import asyncio
import ssl
import time
from dataclasses import dataclass, field
from pathlib import Path

import h2.config
import h2.connection
import h2.events
import h2.settings
import httpx
from hyperframe.frame import DataFrame
from stream_cap import build_capped_client

HERE = Path(__file__).parent
CERT_PATH = HERE / "cert.pem"
KEY_PATH = HERE / "key.pem"

N_REQUESTS = 6


@dataclass
class ConnRecord:
    """One accepted TCP connection, and what the server saw happen on it."""

    index: int
    h2: h2.connection.H2Connection
    writer: asyncio.StreamWriter
    streams: dict[int, str] = field(default_factory=dict)
    open_streams: set[int] = field(default_factory=set)
    max_concurrent: int = 0
    goaway_sent: bool = False


class CountingH2Server:
    def __init__(
        self,
        *,
        expected_requests: int,
        advertised_max_concurrent_streams: int | None = None,
        auto_finish_delay: float | None = None,
    ) -> None:
        self.expected = expected_requests
        self.advertised = advertised_max_concurrent_streams
        self.auto_finish_delay = auto_finish_delay
        self.records: list[ConnRecord] = []
        self.accept_count = 0
        self.requests_seen = 0
        self.all_arrived = asyncio.Event()
        self._tasks: set[asyncio.Task[None]] = set()

    # --- server side ---

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        index = self.accept_count
        self.accept_count += 1
        conn = h2.connection.H2Connection(config=h2.config.H2Configuration(client_side=False))
        if self.advertised is not None:
            # Set before initiate_connection() so the value rides the *initial* SETTINGS frame, which is how a real server advertises it. Sending it as a second, later SETTINGS frame is a different scenario and httpcore mishandles that one -- see the report.
            conn.local_settings = h2.settings.Settings(
                client=False,
                initial_values={h2.settings.SettingCodes.MAX_CONCURRENT_STREAMS: self.advertised},
            )
        conn.initiate_connection()
        writer.write(conn.data_to_send())
        await writer.drain()

        record = ConnRecord(index=index, h2=conn, writer=writer)
        self.records.append(record)

        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                for event in conn.receive_data(data):
                    if isinstance(event, h2.events.RequestReceived):
                        await self._on_request(record, event)
                out = conn.data_to_send()
                if out and not record.goaway_sent:
                    writer.write(out)
                    await writer.drain()
        except (ConnectionResetError, BrokenPipeError, ssl.SSLError):
            # The client hanging up mid-experiment is an expected end for this harness; nothing here needs to survive it.
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def _on_request(self, record: ConnRecord, event: h2.events.RequestReceived) -> None:
        stream_id = event.stream_id
        path = dict(event.headers)[b":path"].decode()
        record.streams[stream_id] = path
        record.open_streams.add(stream_id)
        record.max_concurrent = max(record.max_concurrent, len(record.open_streams))
        self.requests_seen += 1

        record.h2.send_headers(stream_id, [(":status", "200"), ("content-type", "text/event-stream")])
        record.h2.send_data(stream_id, b"data: start\n\n")
        record.writer.write(record.h2.data_to_send())
        await record.writer.drain()

        if self.auto_finish_delay is not None:
            task = asyncio.create_task(self._auto_finish(record, stream_id))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        if self.requests_seen >= self.expected:
            self.all_arrived.set()

    async def _auto_finish(self, record: ConnRecord, stream_id: int) -> None:
        await asyncio.sleep(self.auto_finish_delay or 0.0)
        self.finish_stream(record, stream_id)
        record.writer.write(record.h2.data_to_send())
        await record.writer.drain()

    def finish_stream(self, record: ConnRecord, stream_id: int) -> None:
        record.open_streams.discard(stream_id)
        if record.goaway_sent:
            # h2's own connection state machine goes to CLOSED on SEND_GOAWAY and then refuses SEND_DATA, so an RFC-9113-6.8-compliant "in-flight streams may still complete" tail has to be hand-crafted onto the wire.
            raw = DataFrame(stream_id=stream_id, data=b"data: bye\n\n", flags=["END_STREAM"]).serialize()
            record.writer.write(raw)
        else:
            record.h2.send_data(stream_id, b"data: bye\n\n", end_stream=True)

    def send_goaway(self, record: ConnRecord) -> None:
        record.h2.close_connection(error_code=0, last_stream_id=2**31 - 1)
        record.writer.write(record.h2.data_to_send())
        record.goaway_sent = True

    def stream_map(self) -> dict[str, int]:
        """path -> server connection index."""
        return {path: rec.index for rec in self.records for path in rec.streams.values()}


async def start_server(server: CountingH2Server) -> tuple[asyncio.AbstractServer, int]:
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(certfile=str(CERT_PATH), keyfile=str(KEY_PATH))
    ssl_ctx.set_alpn_protocols(["h2"])
    aio_server = await asyncio.start_server(server.handle, host="127.0.0.1", port=0, ssl=ssl_ctx)
    return aio_server, aio_server.sockets[0].getsockname()[1]


# --- client side ---


def client_ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=str(CERT_PATH))


async def one_request(client: httpx.AsyncClient, url: str, index: int, results: dict[int, str]) -> None:
    try:
        async with client.stream("GET", url) as resp:
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk
            results[index] = f"OK   http/{resp.http_version} body={body!r}"
    except BaseException as exc:
        results[index] = f"FAIL {type(exc).__module__}.{type(exc).__qualname__}: {exc}"


async def drive(
    clients: list[httpx.AsyncClient],
    port: int,
    n: int,
    results: dict[int, str],
) -> None:
    tasks = [
        asyncio.create_task(one_request(clients[i % len(clients)], f"https://127.0.0.1:{port}/req/{i}", i, results))
        for i in range(n)
    ]
    await asyncio.gather(*tasks)


def report(title: str, server: CountingH2Server, results: dict[int, str], elapsed: float) -> None:
    print(f"  TCP connections accepted by server: {server.accept_count}")
    for rec in server.records:
        paths = sorted(rec.streams.values())
        print(
            f"    conn#{rec.index}: {len(rec.streams)} stream(s) {paths} "
            f"max_concurrent={rec.max_concurrent} goaway_sent={rec.goaway_sent}"
        )
    smap = server.stream_map()
    for i in sorted(results):
        conn = smap.get(f"/req/{i}", "?")
        print(f"    req {i} (served on conn#{conn}): {results[i]}")
    ok = sum(1 for v in results.values() if v.startswith("OK"))
    print(f"  summary: {ok}/{len(results)} OK, {len(results) - ok} FAIL, wall {elapsed:.2f}s")


class CountingH11Server:
    """The same measurement for plain HTTP/1.1, so "cap=1 vs just turning HTTP/2 off" can be compared rather than argued.

    Chunked SSE, one request per connection, and the ability to abruptly drop one connection mid-response.
    """

    def __init__(self, *, expected_requests: int, keep_alive: bool = False) -> None:
        self.expected = expected_requests
        self.keep_alive = keep_alive
        self.accept_count = 0
        self.requests_seen = 0
        self.all_arrived = asyncio.Event()
        self.conns: list[tuple[int, str, asyncio.StreamWriter]] = []

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        index = self.accept_count
        self.accept_count += 1
        try:
            while True:
                request_line = await reader.readline()
                if not request_line:
                    break
                path = request_line.split()[1].decode()
                while True:
                    line = await reader.readline()
                    if line in (b"\r\n", b"\n", b""):
                        break
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n"
                )
                writer.write(b"d\r\ndata: start\n\n\r\n")
                await writer.drain()
                self.conns.append((index, path, writer))
                self.requests_seen += 1
                if self.requests_seen >= self.expected:
                    self.all_arrived.set()
                if not self.keep_alive:
                    return
                # keep_alive: go back and read another request on this same TCP connection, so that "the server refused to reuse it" is never the reason a reuse experiment fails.
        except (ConnectionResetError, BrokenPipeError, ssl.SSLError, OSError):
            pass

    def finish(self, writer: asyncio.StreamWriter) -> None:
        writer.write(b"b\r\ndata: bye\n\n\r\n0\r\n\r\n")

    def stream_map(self) -> dict[str, int]:
        return {path: index for index, path, _ in self.conns}


async def exp_http11_comparison() -> None:
    label = "http11_no_h2"
    title = (
        "The alternative already available in this project: upstream_transport.http2 = false. 6 concurrent streaming "
        "GETs over HTTP/1.1, then one connection is abruptly killed mid-response. Prediction: 6 TCP connections and "
        "exactly 1 casualty -- i.e. numerically identical to cap=1, with no httpcore private API involved at all."
    )
    print("=" * 110)
    print(f"EXPERIMENT: {label}")
    print(f"  {title}")
    print("-" * 110)
    server = CountingH11Server(expected_requests=N_REQUESTS)
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(certfile=str(CERT_PATH), keyfile=str(KEY_PATH))
    ssl_ctx.set_alpn_protocols(["http/1.1"])
    aio_server = await asyncio.start_server(server.handle, host="127.0.0.1", port=0, ssl=ssl_ctx)
    port = aio_server.sockets[0].getsockname()[1]

    client = httpx.AsyncClient(http2=False, verify=client_ssl_context(), timeout=15.0)
    results: dict[int, str] = {}
    started = time.monotonic()
    try:
        driver = asyncio.create_task(drive([client], port, N_REQUESTS, results))
        await asyncio.wait_for(server.all_arrived.wait(), timeout=10.0)
        await asyncio.sleep(0.3)
        victim_index, victim_path, victim_writer = server.conns[0]
        print(f"  >>> abruptly dropping conn#{victim_index} ({victim_path}) mid-response")
        victim_writer.transport.abort()
        await asyncio.sleep(0.3)
        for index, _, writer in server.conns:
            if index == victim_index:
                continue
            server.finish(writer)
            await writer.drain()
        await driver
    finally:
        aio_server.close()
    elapsed = time.monotonic() - started
    await client.aclose()

    print(f"  TCP connections accepted by server: {server.accept_count}")
    smap = server.stream_map()
    for i in sorted(results):
        print(f"    req {i} (served on conn#{smap.get(f'/req/{i}', '?')}): {results[i]}")
    ok = sum(1 for v in results.values() if v.startswith("OK"))
    print(f"  summary: {ok}/{len(results)} OK, {len(results) - ok} FAIL, wall {elapsed:.2f}s")
    print()


async def exp_early_close_reuse() -> None:
    """The one place cap=1 h2 and HTTP/1.1 are NOT equivalent, measured rather than read.

    httpcore's h11 connection closes itself whenever a response is released before both sides reached DONE (`http11.py:238-249`); the h2 connection just frees the stream and stays in the pool (`http2.py:409-419`). This project does abandon upstream SSE responses early (client cancels), so the difference is real. Two sequential requests, each read one chunk and then closed early: count how many TCP connections the server had to accept.
    """
    print("=" * 110)
    print("EXPERIMENT: early_close_reuse")
    print(
        "  Two SEQUENTIAL requests, each closed after one chunk (simulating a cancelled downstream). "
        "Prediction: cap=1 HTTP/2 reuses one connection (1 accept); HTTP/1.1 must reconnect (2 accepts)."
    )
    print("-" * 110)

    # --- HTTP/2 with cap=1 ---
    h2_server = CountingH2Server(expected_requests=10**6)
    h2_aio, h2_port = await start_server(h2_server)
    h2_client = build_capped_client(
        ssl_context=client_ssl_context(), max_streams_per_connection=1, timeout=15.0
    )
    try:
        for i in range(2):
            ctx = h2_client.stream("GET", f"https://127.0.0.1:{h2_port}/early/{i}")
            resp = await ctx.__aenter__()
            first = await resp.aiter_bytes().__anext__()
            await ctx.__aexit__(None, None, None)
            print(f"    h2 cap=1  request {i}: got {first!r}, closed early")
            await asyncio.sleep(0.1)
    finally:
        h2_aio.close()
        await h2_client.aclose()
    h2_streams = [(rec.index, sorted(rec.streams)) for rec in h2_server.records]
    print(f"  HTTP/2 cap=1: server accepted {h2_server.accept_count} TCP connection(s); stream ids per conn: {h2_streams}")

    # --- HTTP/1.1 ---
    h11_server = CountingH11Server(expected_requests=10**6, keep_alive=True)
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(certfile=str(CERT_PATH), keyfile=str(KEY_PATH))
    ssl_ctx.set_alpn_protocols(["http/1.1"])
    h11_aio = await asyncio.start_server(h11_server.handle, host="127.0.0.1", port=0, ssl=ssl_ctx)
    h11_port = h11_aio.sockets[0].getsockname()[1]
    h11_client = httpx.AsyncClient(http2=False, verify=client_ssl_context(), timeout=15.0)
    try:
        for i in range(2):
            ctx = h11_client.stream("GET", f"https://127.0.0.1:{h11_port}/early/{i}")
            resp = await ctx.__aenter__()
            first = await resp.aiter_bytes().__anext__()
            await ctx.__aexit__(None, None, None)
            print(f"    http/1.1  request {i}: got {first!r}, closed early")
            await asyncio.sleep(0.1)
    finally:
        h11_aio.close()
        await h11_client.aclose()
    print(f"  HTTP/1.1: server accepted {h11_server.accept_count} TCP connection(s)")
    print(
        "  reading: a difference here means HTTP/1.1 pays an extra TCP+TLS handshake "
        "(~155ms against api.githubcopilot.com) every time a response is abandoned early."
    )
    print()


# --- experiments ---


async def exp_streams_and_connections(*, cap: int | None, n_clients: int, title: str, label: str) -> None:
    print("=" * 110)
    print(f"EXPERIMENT: {label}")
    print(f"  {title}")
    print("-" * 110)
    server = CountingH2Server(expected_requests=N_REQUESTS)
    aio_server, port = await start_server(server)
    ssl_ctx = client_ssl_context()

    clients: list[httpx.AsyncClient] = []
    for _ in range(n_clients):
        if cap is None:
            clients.append(httpx.AsyncClient(http2=True, verify=client_ssl_context(), timeout=15.0))
        else:
            clients.append(build_capped_client(ssl_context=ssl_ctx, max_streams_per_connection=cap, timeout=15.0))

    results: dict[int, str] = {}
    started = time.monotonic()
    try:
        driver = asyncio.create_task(drive(clients, port, N_REQUESTS, results))
        await asyncio.wait_for(server.all_arrived.wait(), timeout=10.0)
        await asyncio.sleep(0.3)
        # Every request is now in flight on a known connection; end them all cleanly.
        for rec in server.records:
            for stream_id in list(rec.open_streams):
                server.finish_stream(rec, stream_id)
            rec.writer.write(rec.h2.data_to_send())
            await rec.writer.drain()
        await driver
    finally:
        # `async with aio_server` is deliberately not used: its __aexit__ awaits wait_closed(), which since 3.12.1 blocks until every connection handler task has finished, and those are parked in reader.read() until the client hangs up. Closing the listener is all this harness needs.
        aio_server.close()
    elapsed = time.monotonic() - started
    for client in clients:
        await client.aclose()
    report(title="", server=server, results=results, elapsed=elapsed)
    print()


async def exp_goaway(*, cap: int | None, title: str, label: str) -> None:
    print("=" * 110)
    print(f"EXPERIMENT: {label}")
    print(f"  {title}")
    print("-" * 110)
    server = CountingH2Server(expected_requests=N_REQUESTS)
    aio_server, port = await start_server(server)
    ssl_ctx = client_ssl_context()
    if cap is None:
        client = httpx.AsyncClient(http2=True, verify=ssl_ctx, timeout=15.0)
    else:
        client = build_capped_client(ssl_context=ssl_ctx, max_streams_per_connection=cap, timeout=15.0)

    results: dict[int, str] = {}
    started = time.monotonic()
    try:
        driver = asyncio.create_task(drive([client], port, N_REQUESTS, results))
        await asyncio.wait_for(server.all_arrived.wait(), timeout=10.0)
        await asyncio.sleep(0.3)

        victim = server.records[0]
        print(f"  >>> sending GOAWAY(error_code=0, last_stream_id=2**31-1) on conn#{victim.index} only")
        server.send_goaway(victim)
        await victim.writer.drain()
        await asyncio.sleep(0.5)

        # Then end every stream on every connection, victim included -- RFC 9113 6.8 says in-flight streams "might still complete successfully", so a compliant server would.
        for rec in server.records:
            try:
                for stream_id in list(rec.open_streams):
                    server.finish_stream(rec, stream_id)
                if not rec.goaway_sent:
                    rec.writer.write(rec.h2.data_to_send())
                await rec.writer.drain()
            except (ConnectionResetError, BrokenPipeError, ssl.SSLError, OSError) as exc:
                # Expected on the victim: httpcore tears the socket down the moment it decides the GOAWAY is fatal, so the tail this server would have delivered has nowhere to go. Recording that is part of the result.
                print(f"  (conn#{rec.index}: client already gone when the tail was written -- {type(exc).__name__}: {exc})")
        await driver
    finally:
        aio_server.close()
    elapsed = time.monotonic() - started
    await client.aclose()
    report(title="", server=server, results=results, elapsed=elapsed)
    print()


async def exp_advertised_mcs(*, cap: int | None, advertised: int, hold: float, label: str, title: str, reading: str) -> None:
    print("=" * 110)
    print(f"EXPERIMENT: {label}")
    print(f"  {title}")
    print("-" * 110)
    server = CountingH2Server(
        expected_requests=N_REQUESTS, advertised_max_concurrent_streams=advertised, auto_finish_delay=hold
    )
    aio_server, port = await start_server(server)
    ssl_ctx = client_ssl_context()
    if cap is None:
        client = httpx.AsyncClient(http2=True, verify=ssl_ctx, timeout=15.0)
    else:
        client = build_capped_client(ssl_context=ssl_ctx, max_streams_per_connection=cap, timeout=15.0)
    results: dict[int, str] = {}
    started = time.monotonic()
    try:
        await drive([client], port, N_REQUESTS, results)
    finally:
        aio_server.close()
    elapsed = time.monotonic() - started
    await client.aclose()
    report(title="", server=server, results=results, elapsed=elapsed)
    print(f"  reading: {reading}")
    print()


async def main() -> None:
    await exp_streams_and_connections(
        cap=None,
        n_clients=1,
        label="baseline_no_cap",
        title=(
            "Positive control for the measurement itself. 6 concurrent streaming GETs on a stock "
            "httpx.AsyncClient(http2=True). If these do not all land on one TCP connection, nothing below means anything."
        ),
    )
    await exp_streams_and_connections(
        cap=2,
        n_clients=1,
        label="cap2",
        title=(
            "Candidate 2. Same 6 requests through StreamCappedPool(max_streams_per_connection=2). "
            "Prediction: ceil(6/2)=3 TCP connections, 2 streams each."
        ),
    )
    await exp_goaway(
        cap=None,
        label="no_cap_goaway",
        title=(
            "Local reproduction of the production incident. 6 streams share one connection; the server sends one "
            "GOAWAY(NO_ERROR, last_stream_id=2**31-1) and then still delivers every stream's terminating DATA. "
            "Prediction: all 6 die anyway."
        ),
    )
    await exp_goaway(
        cap=2,
        label="cap2_goaway",
        title=(
            "The point of the whole exercise. Same GOAWAY, but with cap=2 the 6 streams are spread over 3 connections "
            "and only conn#0 is hit. Prediction: exactly 2 FAIL, 4 OK."
        ),
    )
    await exp_streams_and_connections(
        cap=1,
        n_clients=1,
        label="cap1",
        title=(
            "The value the sister project copilot-api-js actually shipped (b5892380f, 2026-07-22). cap=1 is one "
            "stream per connection. Prediction: 6 TCP connections for 6 concurrent requests -- which is the HTTP/1.1 "
            "connection model wearing HTTP/2 framing."
        ),
    )
    await exp_goaway(
        cap=1,
        label="cap1_goaway",
        title=(
            "cap=1 under the same GOAWAY. Prediction: exactly 1 FAIL, 5 OK. A multi-victim event is impossible by "
            "construction, because no connection ever carries two streams."
        ),
    )
    await exp_http11_comparison()
    await exp_early_close_reuse()
    await exp_advertised_mcs(
        cap=None,
        advertised=2,
        hold=0.4,
        label="server_advertised_mcs",
        title=(
            "Candidate 3. Stock pool, no client-side cap. The SERVER advertises SETTINGS_MAX_CONCURRENT_STREAMS=2 in "
            "its initial SETTINGS, and each stream is auto-finished 0.4s after it opens. Does a low "
            "MAX_CONCURRENT_STREAMS make httpcore open more connections, or does it throttle onto the one it has?"
        ),
        reading=(
            "6 requests x 0.4s hold. One connection at concurrency 2 means three waves, ~1.2s. "
            "One connection at concurrency 6 would be ~0.4s. Three connections at 2 would also be ~0.4s."
        ),
    )
    await exp_advertised_mcs(
        cap=2,
        advertised=2,
        hold=0.4,
        label="cap2_plus_advertised_mcs2",
        title=(
            "Our cap equal to what the server advertises. Prediction: 3 connections x 2 streams, and no throttling, "
            "because no connection ever wants more slots than the server granted it."
        ),
        reading="~0.4s means no serialisation happened; ~1.2s would mean the cap did not prevent queueing.",
    )
    await exp_advertised_mcs(
        cap=4,
        advertised=2,
        hold=0.4,
        label="cap4_above_advertised_mcs2",
        title=(
            "Our cap set ABOVE what the server advertises. 6 requests, cap=4 -> 2 connections (4 and 2), but the "
            "server only permits 2 concurrent streams each. Shows what happens when the two numbers disagree."
        ),
        reading="The connection holding 4 assignments can only run 2 at a time, so it costs an extra wave (~0.8s).",
    )
    await exp_streams_and_connections(
        cap=None,
        n_clients=3,
        label="sharded_clients",
        title=(
            "Candidate 4, the dumb fallback. Three independent httpx.AsyncClient instances, requests round-robined. "
            "Prediction: 3 TCP connections, 2 streams each -- same shape as cap2, with no private API touched."
        ),
    )


if __name__ == "__main__":
    asyncio.run(main())
