"""What does an extra HTTP/2 connection actually cost, and what does the real upstream advertise?

Two probes, both cheap and both answering questions the cap decision depends on:

- `probe_upstream_settings()` opens a TLS+ALPN-h2 connection to api.githubcopilot.com, reads the server's initial SETTINGS frame, and hangs up. No credentials, no HTTP request is ever sent, nothing is written past the h2 connection preface. It reports the server's advertised SETTINGS_MAX_CONCURRENT_STREAMS -- the ceiling our own cap has to sit under to mean anything -- plus separated TCP-connect and TLS-handshake timings, which is the per-extra-connection latency the cap buys its safety with.
- `probe_memory()` opens a growing number of real httpx HTTP/2 connections against the local harness server and reports RSS, to size the per-connection memory cost.

Run: cd /home/xp/src/ghc-api-proxy-py/exp/260820-h2-stream-cap && /home/xp/src/ghc-api-proxy-py/.venv/bin/python probe_costs.py
"""

from __future__ import annotations

import asyncio
import gc
import os
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

import h2.config
import h2.connection
import h2.events
import h2.settings
import httpx  # noqa: F401  -- imported for the type of the objects held open by probe_memory
from run_poc import client_ssl_context
from stream_cap import build_capped_client

UPSTREAM_HOSTS = ["api.githubcopilot.com", "api.github.com"]


def rss_kb() -> int:
    with open("/proc/self/statm", encoding="ascii") as handle:
        return int(handle.read().split()[1]) * (os.sysconf("SC_PAGE_SIZE") // 1024)


def fd_count() -> int:
    return len(os.listdir("/proc/self/fd"))


def probe_upstream_settings(host: str, samples: int = 3) -> None:
    print(f"--- {host} ---")
    for attempt in range(samples):
        try:
            t0 = time.perf_counter()
            raw = socket.create_connection((host, 443), timeout=10.0)
            t1 = time.perf_counter()

            ctx = ssl.create_default_context()
            ctx.set_alpn_protocols(["h2", "http/1.1"])
            sock = ctx.wrap_socket(raw, server_hostname=host)
            t2 = time.perf_counter()

            alpn = sock.selected_alpn_protocol()
            settings: dict[str, int] = {}
            if alpn == "h2":
                conn = h2.connection.H2Connection(config=h2.config.H2Configuration(client_side=True))
                conn.initiate_connection()
                sock.sendall(conn.data_to_send())
                sock.settimeout(5.0)
                deadline = time.perf_counter() + 5.0
                while not settings and time.perf_counter() < deadline:
                    data = sock.recv(65536)
                    if not data:
                        break
                    for event in conn.receive_data(data):
                        if isinstance(event, h2.events.RemoteSettingsChanged):
                            for code, change in event.changed_settings.items():
                                name = getattr(code, "name", str(code))
                                settings[name] = change.new_value
                    out = conn.data_to_send()
                    if out:
                        sock.sendall(out)
            sock.close()
            print(
                f"  sample {attempt}: alpn={alpn!r} tcp_connect={1000 * (t1 - t0):.1f}ms "
                f"tls_handshake={1000 * (t2 - t1):.1f}ms total={1000 * (t2 - t0):.1f}ms"
            )
            if settings:
                print(f"    server SETTINGS: {settings}")
                mcs = settings.get("MAX_CONCURRENT_STREAMS")
                print(f"    -> advertised SETTINGS_MAX_CONCURRENT_STREAMS = {mcs}")
            elif alpn == "h2":
                print("    (no SETTINGS observed within the deadline)")
        except Exception as exc:
            print(f"  sample {attempt}: FAILED {type(exc).__name__}: {exc}")
    print()


def probe_alpn_http11(host: str, samples: int = 2) -> None:
    """Does the upstream still serve us if we stop offering h2 at all?

    This is the question behind "cap=1 versus just setting upstream_transport.http2 = false". If the edge refuses or degrades on an http/1.1-only ALPN offer, that switch is not a free alternative. Nothing is sent beyond the TLS handshake.
    """
    print(f"--- {host}: ALPN offering ONLY http/1.1 ---")
    for attempt in range(samples):
        try:
            t0 = time.perf_counter()
            raw = socket.create_connection((host, 443), timeout=10.0)
            ctx = ssl.create_default_context()
            ctx.set_alpn_protocols(["http/1.1"])
            sock = ctx.wrap_socket(raw, server_hostname=host)
            t1 = time.perf_counter()
            print(
                f"  sample {attempt}: negotiated alpn={sock.selected_alpn_protocol()!r} "
                f"tls_version={sock.version()} total={1000 * (t1 - t0):.1f}ms"
            )
            sock.close()
        except Exception as exc:
            print(f"  sample {attempt}: FAILED {type(exc).__name__}: {exc}")
    print()


async def probe_memory() -> None:
    """RSS cost of N live HTTP/2 connections inside ONE client.

    The cap itself is used as the instrument: `max_streams_per_connection=1` forces exactly one TCP connection per in-flight request, so the number below is the marginal cost of a *connection*, not of an `AsyncClient`. The h2 server runs in a separate process, so the RSS delta is the client side only.
    """
    counts = [1, 10, 50, 100]
    child = subprocess.Popen(
        [sys.executable, "-u", str(Path(__file__).with_name("serve_h2.py"))],
        cwd=str(Path(__file__).parent),
        stdout=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None
    port = int(child.stdout.readline().strip())
    client = build_capped_client(ssl_context=client_ssl_context(), max_streams_per_connection=1, timeout=60.0)
    held: list[object] = []
    print("--- client-side RSS vs live HTTP/2 connections (one client, cap=1, one open stream each) ---")
    print(f"  h2 server running in pid {child.pid} on port {port}")
    try:
        gc.collect()
        base = rss_kb()
        print(f"  baseline (client built, 0 connections): rss={base} KiB, fds={fd_count()}")
        opened = 0
        for target in counts:
            while opened < target:
                ctx = client.stream("GET", f"https://127.0.0.1:{port}/mem/{opened}")
                resp = await ctx.__aenter__()
                # The iterator has to be *kept*, not created and dropped: an abandoned httpx body generator gets finalised by the event loop, GeneratorExit reaches `PoolByteStream.__aiter__`, and its `except BaseException: await self.aclose()` removes the request from `pool._requests` -- releasing the very slot this probe is trying to hold. Measured the hard way: the first version of this probe reported 100 connections while the server had accepted 2.
                iterator = resp.aiter_bytes()
                await iterator.__anext__()
                held.append((ctx, resp, iterator))
                opened += 1
            gc.collect()
            now = rss_kb()
            pool_conns = len(client._transport._pool.connections)  # type: ignore[attr-defined]
            print(
                f"  {opened} connections: rss={now} KiB  delta={now - base} KiB  "
                f"per-connection={(now - base) / opened:.1f} KiB  fds={fd_count()}  "
                f"(pool holds {pool_conns} connections)"
            )
    finally:
        await client.aclose()
        child.terminate()
        child.wait(timeout=5)
    print()


async def main() -> None:
    print("=" * 100)
    print("PROBE 1: what the real upstream advertises, and what a fresh connection costs in latency")
    print("  Unauthenticated. TLS handshake + h2 connection preface only; no HTTP request is sent.")
    print("=" * 100)
    for host in UPSTREAM_HOSTS:
        probe_upstream_settings(host)

    print("=" * 100)
    print("PROBE 1b: does the upstream accept an http/1.1-only ALPN offer?")
    print("  This is what `upstream_transport.http2 = false` makes httpx send.")
    print("=" * 100)
    for host in UPSTREAM_HOSTS:
        probe_alpn_http11(host)

    print("=" * 100)
    print("PROBE 2: memory cost of extra connections")
    print("=" * 100)
    await probe_memory()


if __name__ == "__main__":
    asyncio.run(main())
