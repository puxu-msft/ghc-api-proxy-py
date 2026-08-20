"""Do repeated waits accumulate callbacks on the pull task?"""
import asyncio

def cbs(fut):
    raw = fut._callbacks or []
    out = []
    for cb in raw:
        f = cb[0] if isinstance(cb, tuple) else cb
        out.append(getattr(f, "__name__", repr(f)))
    return out

async def pull():
    await asyncio.sleep(1.0)
    return "v"

async def main():
    task = asyncio.ensure_future(pull())
    for i in range(4):
        await asyncio.wait({task}, timeout=0.05)
        print(f"new, after wait {i}:", cbs(task))
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

asyncio.run(main())
