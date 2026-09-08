"""Same abandon-mid-pull shape against session_liveness_stream, for contrast."""
import asyncio, gc
from app.streaming.keepalive import session_liveness_stream

async def main():
    state = {"closed": False, "in_flight": False}
    async def upstream():
        try:
            yield b"a"
            yield b"b"
            state["in_flight"] = True
            await asyncio.sleep(3600)
        finally:
            state["closed"] = True

    agen = session_liveness_stream(
        upstream(), heartbeat_interval_seconds=0,
        heartbeat=b": ping\n\n", upstream_idle_timeout_seconds=0,
    )
    it = agen.__aiter__()
    for _ in range(2):
        await anext(it)
    waiter = asyncio.ensure_future(anext(it))
    await asyncio.sleep(0.05)
    print("upstream reached the hang? ->", state["in_flight"])
    waiter.cancel()
    try:
        await waiter
    except asyncio.CancelledError:
        pass
    try:
        await agen.aclose()
    except BaseException as exc:
        print("aclose raised:", type(exc).__name__, exc)
    print("right after aclose():  upstream closed? ->", state["closed"])
    for _ in range(5):
        await asyncio.sleep(0)
    others = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    print("tasks alive:", [(t.get_name(), "done" if t.done() else "PENDING") for t in others])

asyncio.run(main())
