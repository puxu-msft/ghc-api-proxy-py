"""Minimal instrumented probe: why did baseline_no_cap not see 6 requests arrive?"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from run_poc import CountingH2Server, client_ssl_context, start_server

HERE = Path(__file__).parent


async def monitor(server: CountingH2Server) -> None:
    for _ in range(20):
        await asyncio.sleep(0.5)
        print(
            f"    [monitor] accepts={server.accept_count} requests_seen={server.requests_seen} "
            f"records={[(r.index, sorted(r.streams.values())) for r in server.records]}"
        )


async def one(client: httpx.AsyncClient, port: int, i: int) -> None:
    print(f"    [req {i}] starting")
    try:
        async with client.stream("GET", f"https://127.0.0.1:{port}/req/{i}") as resp:
            print(f"    [req {i}] headers status={resp.status_code} http={resp.http_version}")
            async for chunk in resp.aiter_bytes():
                print(f"    [req {i}] chunk {chunk!r}")
            print(f"    [req {i}] done")
    except BaseException as exc:
        print(f"    [req {i}] EXC {type(exc).__name__}: {exc}")


async def main() -> None:
    server = CountingH2Server(expected_requests=6)
    aio_server, port = await start_server(server)
    client = httpx.AsyncClient(http2=True, verify=client_ssl_context(), timeout=10.0)
    mon = asyncio.create_task(monitor(server))
    tasks = [asyncio.create_task(one(client, port, i)) for i in range(6)]
    try:
        await asyncio.wait_for(server.all_arrived.wait(), timeout=8.0)
        print("    ALL ARRIVED")
    except TimeoutError:
        print(f"    TIMED OUT waiting; requests_seen={server.requests_seen} accepts={server.accept_count}")
    for rec in server.records:
        for sid in list(rec.open_streams):
            server.finish_stream(rec, sid)
        rec.writer.write(rec.h2.data_to_send())
        await rec.writer.drain()
    await asyncio.gather(*tasks, return_exceptions=True)
    mon.cancel()
    await client.aclose()
    aio_server.close()


if __name__ == "__main__":
    asyncio.run(main())
