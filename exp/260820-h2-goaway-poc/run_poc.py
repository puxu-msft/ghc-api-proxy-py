"""Decisive local PoC for the GOAWAY(NO_ERROR, last_stream_id=2**31-1) hypothesis.

Claim under test (see docs/tmp/260820-h2-goaway-poc.md for the write-up): a GOAWAY that RFC 9113 section 6.8 defines as a graceful-shutdown *preamble* (error_code=NO_ERROR, last_stream_id=2**31-1, meaning "stop opening new streams, in-flight streams are fine") gets treated by httpcore 1.0.9 as an unconditional, immediate death sentence for every stream still being read on that connection -- because httpcore's retry branch only fires when `stream_id > last_stream_id`, which can never be true when last_stream_id is 2**31-1.

Everything here is local: a hand-rolled h2 server (TLS + ALPN h2, self-signed cert from gen_cert.py) and a real httpx.AsyncClient(http2=True) talking to it over 127.0.0.1. No production code is touched, no real upstream is contacted.

Run: /home/xp/src/ghc-api-proxy-py/.venv/bin/python run_poc.py
"""

from __future__ import annotations

import asyncio
import ssl
import traceback
from pathlib import Path

import h2.config
import h2.connection
import h2.events
import httpcore
import httpx
from hyperframe.frame import DataFrame, Frame, GoAwayFrame

HERE = Path(__file__).parent
CERT_PATH = HERE / "cert.pem"
KEY_PATH = HERE / "key.pem"


def describe_goaway_bytes(raw: bytes) -> str:
    """Parse raw wire bytes with hyperframe and describe the GOAWAY frame in them.

    This is the "did the frame I *think* I sent actually go out on the wire"
    check the task asked for, independent of the h2 library's own bookkeeping.
    """
    header, length = Frame.parse_frame_header(raw[:9])
    if not isinstance(header, GoAwayFrame):
        return f"NOT a GOAWAY frame: {header!r}"
    header.parse_body(memoryview(raw[9 : 9 + length]))
    return (
        f"GOAWAY frame on wire: last_stream_id={header.last_stream_id} "
        f"error_code={header.error_code} additional_data={header.additional_data!r}"
    )


class Server:
    """A single-connection-at-a-time raw h2 server used to script exact wire behavior.

    Uses the `h2` library for the legitimate part of the exchange (handshake, request headers, first response headers/data, and the GOAWAY itself via close_connection()). For frames we need to send *after* close_connection(), we bypass h2 entirely and hand-craft wire bytes with hyperframe, because h2's own connection-level state machine hard-transitions to CLOSED on SEND_GOAWAY and then refuses SEND_DATA (confirmed separately, see report). That refusal is itself evidence about the shape of the RFC 9113 section 6.8 double-GOAWAY graceful-shutdown pattern versus what the `h2` library supports.
    """

    def __init__(self, mode: str):
        self.mode = mode
        self.goaway_wire_bytes: bytes | None = None

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        config = h2.config.H2Configuration(client_side=False)
        conn = h2.connection.H2Connection(config=config)
        conn.initiate_connection()
        writer.write(conn.data_to_send())
        await writer.drain()

        stream_id: int | None = None
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                events = conn.receive_data(data)
                outbound_needed = False
                for event in events:
                    if isinstance(event, h2.events.RequestReceived):
                        stream_id = event.stream_id
                        await self._on_request(conn, writer, stream_id)
                        return
                    outbound_needed = True
                if outbound_needed:
                    out = conn.data_to_send()
                    if out:
                        writer.write(out)
                        await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def _on_request(
        self,
        conn: h2.connection.H2Connection,
        writer: asyncio.StreamWriter,
        stream_id: int,
    ) -> None:
        mode = self.mode

        if mode in ("goaway_before_headers_sentinel", "goaway_before_headers_low"):
            # Never send response headers at all. Fire GOAWAY immediately.
            last_stream_id = 2**31 - 1 if mode.endswith("sentinel") else 0
            conn.close_connection(error_code=0, last_stream_id=last_stream_id)
            out = conn.data_to_send()
            self.goaway_wire_bytes = out
            writer.write(out)
            await writer.drain()
            await asyncio.sleep(1.0)
            writer.close()
            return

        # All other modes: respond normally with headers + first DATA chunk.
        conn.send_headers(
            stream_id,
            [(":status", "200"), ("content-type", "text/event-stream")],
        )
        conn.send_data(stream_id, b"data: hello\n\n")
        writer.write(conn.data_to_send())
        await writer.drain()

        if mode == "control":
            await asyncio.sleep(1.0)
            conn.send_data(stream_id, b"data: bye\n\n", end_stream=True)
            writer.write(conn.data_to_send())
            await writer.drain()
            await asyncio.sleep(0.2)
            writer.close()
            return

        if mode in ("goaway_sentinel_separate_reads", "goaway_sentinel_same_write"):
            conn.close_connection(error_code=0, last_stream_id=2**31 - 1)
            goaway_bytes = conn.data_to_send()
            self.goaway_wire_bytes = goaway_bytes

            # The second DATA frame can no longer go through conn.send_data(): h2's own connection state machine is now CLOSED and refuses SEND_DATA regardless of the GOAWAY's error_code/last_stream_id. Hand-craft it directly so we can put it on the wire exactly as a real RFC-9113-compliant graceful-shutdown server would.
            raw_data2 = DataFrame(
                stream_id=stream_id, data=b"data: bye\n\n", flags=["END_STREAM"]
            ).serialize()

            if mode == "goaway_sentinel_same_write":
                # Best-effort bid to land GOAWAY + DATA2 in the same client-side read(): one write() call, no intervening await/sleep.
                writer.write(goaway_bytes + raw_data2)
                await writer.drain()
                await asyncio.sleep(0.2)
                writer.close()
                return

            # separate_reads: force GOAWAY and DATA2 into distinct TCP reads by writing them 1s apart.
            writer.write(goaway_bytes)
            await writer.drain()
            await asyncio.sleep(1.0)
            writer.write(raw_data2)
            await writer.drain()
            await asyncio.sleep(0.2)
            writer.close()
            return

        raise ValueError(f"unknown mode {mode!r}")


async def start_server(mode: str) -> tuple[asyncio.AbstractServer, int, Server]:
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(certfile=str(CERT_PATH), keyfile=str(KEY_PATH))
    ssl_ctx.set_alpn_protocols(["h2"])

    srv = Server(mode)
    server = await asyncio.start_server(
        srv.handle, host="127.0.0.1", port=0, ssl=ssl_ctx
    )
    port = server.sockets[0].getsockname()[1]
    return server, port, srv


async def run_client(port: int) -> None:
    ssl_ctx = ssl.create_default_context(cafile=str(CERT_PATH))
    client_kwargs = {"http2": True, "verify": ssl_ctx, "timeout": 5.0}
    async with httpx.AsyncClient(**client_kwargs) as client:
        try:
            async with client.stream(
                "GET", f"https://127.0.0.1:{port}/test"
            ) as resp:
                print(f"  status: {resp.status_code}")
                print(f"  http_version: {resp.http_version}")
                chunks: list[bytes] = []
                async for chunk in resp.aiter_bytes():
                    print(f"  chunk received: {chunk!r}")
                    chunks.append(chunk)
                total = b"".join(chunks)
                print(f"  STREAM ENDED NORMALLY. total bytes: {total!r}")
        except BaseException as exc:
            print(f"  EXCEPTION RAISED: {type(exc).__module__}.{type(exc).__qualname__}: {exc!r}")
            print("  full traceback:")
            traceback.print_exc()
            print(f"  is httpcore.RemoteProtocolError: {isinstance(exc, httpcore.RemoteProtocolError)}")
            print(f"  is httpcore.ConnectionNotAvailable: {isinstance(exc, httpcore.ConnectionNotAvailable)}")
            print(f"  is httpx.RemoteProtocolError: {isinstance(exc, httpx.RemoteProtocolError)}")
            import h2.exceptions

            print(f"  is bare h2.exceptions.ProtocolError (not wrapped by httpcore): {type(exc) is h2.exceptions.ProtocolError}")


async def run_experiment(mode: str, title: str) -> None:
    print("=" * 100)
    print(f"EXPERIMENT: {mode}")
    print(f"  {title}")
    print("-" * 100)
    server, port, srv = await start_server(mode)
    async with server:
        await run_client(port)
    if srv.goaway_wire_bytes is not None:
        print(f"  wire-level confirmation: {describe_goaway_bytes(srv.goaway_wire_bytes)}")
    print()


async def main() -> None:
    await run_experiment(
        "control",
        "No GOAWAY at all. Positive control: proves the harness itself (server + "
        "TLS + h2c-over-TLS + httpx client) can deliver two chunks across a 1s "
        "gap and end the stream cleanly. If this fails, nothing else means anything.",
    )
    await run_experiment(
        "goaway_sentinel_separate_reads",
        "Main experiment. Server sends HEADERS+DATA1, then GOAWAY(NO_ERROR, "
        "last_stream_id=2**31-1), then 1s later a legitimate DATA2+END_STREAM for "
        "the SAME still-open stream, in a separate TCP write/read. Tests the "
        "user's hypothesis directly: does httpcore kill the in-flight read before "
        "DATA2 is ever delivered?",
    )
    await run_experiment(
        "goaway_sentinel_same_write",
        "Same scenario, but GOAWAY and DATA2 are written in a single writer.write() "
        "call with no delay, biasing towards both frames landing in the SAME "
        "client-side socket read (and hence the same h2 receive_data() call). "
        "Explores whether the failure mode changes (bare h2.exceptions.ProtocolError "
        "instead of httpcore.RemoteProtocolError) when events are batched.",
    )
    await run_experiment(
        "goaway_before_headers_sentinel",
        "Secondary question. Server sends GOAWAY(last_stream_id=2**31-1) BEFORE "
        "ever sending response headers for the in-flight request. Does the client "
        "get a fatal RemoteProtocolError, or the retryable ConnectionNotAvailable?",
    )
    await run_experiment(
        "goaway_before_headers_low",
        "Falsification-oriented control for the secondary question. Same as above "
        "but last_stream_id=0 (server claims to have fully processed nothing, "
        "including this very request). Prediction: NOW the client should get the "
        "retryable ConnectionNotAvailable, because stream_id(1) > last_stream_id(0) "
        "becomes true. If so, the determining factor is the last_stream_id value, "
        "not 'before vs after headers'.",
    )


if __name__ == "__main__":
    asyncio.run(main())
