"""Isolate: does closing _counted_upstream close its own source, or leave it to GC?"""

import asyncio
import gc
import sys
from collections.abc import AsyncIterator
from types import SimpleNamespace

sys.path.insert(0, "/home/xp/src/ghc-api-proxy-py/src")

from app.pipeline.delivery.sse_source import read_events
from app.server.pipeline_app import _counted_upstream, _tracked_delivery


async def probe(name: str, wrap) -> None:
    closed: list[str] = []

    async def raw() -> AsyncIterator[bytes]:
        try:
            yield b"event: ping\ndata: {}\n\n"
            yield b"event: ping\ndata: {}\n\n"
        except BaseException as exc:  # noqa: BLE001
            closed.append(f"received:{type(exc).__name__}")
            raise
        finally:
            closed.append("closed")

    outer = wrap(raw())
    it = outer.__aiter__()
    await anext(it)
    await outer.aclose()
    print(f"{name:26s} immediately after aclose(): {closed}")
    if not closed:
        del it, outer
        gc.collect()
        await asyncio.sleep(0.05)
        print(f"{'':26s} after del+gc+sleep:        {closed}")


def wrap_counted(src):
    chain = SimpleNamespace(active_requests=SimpleNamespace(add_bytes=lambda *_: None))
    return _counted_upstream(src, chain, "rid", SimpleNamespace(received=0))


def wrap_tracked(src):
    async def passthrough():
        async for c in src:
            yield c

    return _tracked_delivery(passthrough(), SimpleNamespace(finish=lambda: None))


async def main() -> None:
    await probe("read_events (patched)", read_events)
    await probe("_counted_upstream", wrap_counted)
    await probe("_tracked_delivery", wrap_tracked)


asyncio.run(main())
