"""Abandonment noise: close the generator mid-pull, with and without a preceding keep-alive."""
import asyncio, contextlib, gc
from app.pipeline.delivery.stream import _events_with_ping

async def scenario(keepalive_first: bool):
    loop = asyncio.get_running_loop()
    seen = []
    loop.set_exception_handler(lambda l, ctx: seen.append(ctx.get("message")))

    async def feed():
        await asyncio.sleep(1.4)
        return
        yield b""

    interval = 1 if keepalive_first else 0
    agen = _events_with_ping(feed(), interval)
    got = []
    async def consume():
        async for e in agen:
            got.append(e)
    t = asyncio.ensure_future(consume())
    await asyncio.sleep(1.2 if keepalive_first else 0.2)
    t.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await t
    await agen.aclose()
    await asyncio.sleep(1.6 if keepalive_first else 2.6)  # outlast the feed's own end at 1.4s
    gc.collect(); await asyncio.sleep(0.1); gc.collect(); await asyncio.sleep(0.1)
    print(f"abandon keepalive_first={keepalive_first}: yields={got} handler={seen}")
    loop.set_exception_handler(None)

async def main():
    await scenario(True)
    await scenario(False)

asyncio.run(main())
