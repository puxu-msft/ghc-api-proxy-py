"""The general rule behind every shield site: outer cancelled while inner pending, inner then raises."""
import asyncio, contextlib

async def named_coro(delay, exc):
    await asyncio.sleep(delay)
    raise exc

async def agen(delay):
    await asyncio.sleep(delay)
    return
    yield b""

async def run(label, make_task, cancel_after, inner_delay):
    loop = asyncio.get_running_loop()
    seen = []
    loop.set_exception_handler(lambda l, ctx: seen.append((ctx.get("message"), repr(ctx.get("future")))))
    task = make_task()
    async def awaiter():
        await asyncio.shield(task)
    a = asyncio.ensure_future(awaiter())
    await asyncio.sleep(cancel_after)
    a.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await a
    await asyncio.sleep(inner_delay + 0.1)
    with contextlib.suppress(BaseException):
        task.exception()
    await asyncio.sleep(0)
    print(f"{label}: {seen}")
    loop.set_exception_handler(None)

async def main():
    # stream.py shape: ensure_future(anext(async_generator))
    it = agen(0.2).__aiter__()
    await run("A stream.py shape (anext)", lambda: asyncio.ensure_future(anext(it)), 0.05, 0.2)
    # sse.py / keepalive.py shape: create_task(named_coroutine())
    await run("B named-coroutine shape, StopAsyncIteration",
              lambda: asyncio.ensure_future(named_coro(0.2, StopAsyncIteration())), 0.05, 0.2)
    # writer.py shape: a bare Future that later gets an exception
    async def fut_maker():
        pass
    loop = asyncio.get_running_loop()
    f = loop.create_future()
    loop.call_later(0.2, lambda: f.set_exception(RuntimeError("insert failed")))
    await run("C bare-Future shape (writer ack)", lambda: f, 0.05, 0.2)
    # D control: inner cancelled instead of raising -> no log
    t = asyncio.ensure_future(named_coro(5, RuntimeError("x")))
    async def d():
        loop2 = asyncio.get_running_loop()
        seen = []
        loop2.set_exception_handler(lambda l, ctx: seen.append(ctx.get("message")))
        a = asyncio.ensure_future(asyncio.shield(t))
        await asyncio.sleep(0.05)
        a.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await a
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t
        await asyncio.sleep(0.05)
        print("D control (inner cancelled):", seen)
        loop2.set_exception_handler(None)
    await d()

asyncio.run(main())
