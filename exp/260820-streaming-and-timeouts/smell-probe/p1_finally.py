"""Is stream.py:73-75 `finally: if task.done() and not task.cancelled(): task.exception()` reachable-useful?

Claim to test: Future.result() already clears __log_traceback, so the finally is a no-op
in every path where it actually runs, and it never runs in the path that leaks
(`Task exception was never retrieved` on an abandoned pull).
"""
import asyncio


async def main():
    async def gen():
        yield 1
        return

    it = gen().__aiter__()
    t = asyncio.ensure_future(anext(it))
    await asyncio.wait({t})
    print("A yielded value; _log_traceback after result():", t.result(), t._log_traceback)

    t2 = asyncio.ensure_future(anext(it))
    await asyncio.wait({t2})
    try:
        t2.result()
    except StopAsyncIteration:
        pass
    print("B StopAsyncIteration; _log_traceback after result() raised:", t2._log_traceback)
    print("   finally would then call exception(); already False ->", t2._log_traceback)

asyncio.run(main())
