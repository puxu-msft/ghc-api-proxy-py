import asyncio, sys

async def pull(delay, exc=None):
    await asyncio.sleep(delay)
    if exc is not None:
        raise exc
    return "value"

def cbs(fut):
    # peek at the internal callback list
    raw = fut._callbacks or []
    out = []
    for cb in raw:
        f = cb[0] if isinstance(cb, tuple) else cb
        out.append(getattr(f, "__name__", repr(f)))
    return out

async def main():
    loop = asyncio.get_running_loop()
    seen = []
    loop.set_exception_handler(lambda l, ctx: seen.append(ctx.get("message")))

    task = asyncio.ensure_future(pull(0.30, StopAsyncIteration()))
    print("after ensure_future:", cbs(task))
    for i in range(3):
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=0.05)
        except TimeoutError:
            await asyncio.sleep(0)   # let _outer_done_callback run
            print(f"after timeout {i}:", cbs(task))
    # final pull that succeeds
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
    except StopAsyncIteration:
        print("caught StopAsyncIteration from wait_for")
    await asyncio.sleep(0)
    print("handler messages:", seen)

asyncio.run(main())
print("python:", sys.version)
