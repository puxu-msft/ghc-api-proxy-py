"""Language-level semantics the new finally depends on. No project code."""

import asyncio
import sys


async def probe_a() -> None:
    """sys.exception() inside a finally reached by `return` from inside an except block."""
    seen = []

    async def gen():
        try:
            try:
                raise StopAsyncIteration
            except StopAsyncIteration:
                return
            yield 1  # unreachable, makes it a generator
        finally:
            seen.append(("A", repr(sys.exception())))

    async for _ in gen():
        pass
    print("A sys.exception() on the StopAsyncIteration-return path:", seen)


async def probe_b() -> None:
    """Raise a non-GeneratorExit from a generator's finally while aclose() is running."""

    async def gen():
        try:
            yield 1
            yield 2
        finally:
            raise ValueError("cleanup failure")

    g = gen()
    assert await anext(g) == 1
    try:
        await g.aclose()
    except BaseException as exc:
        print("B aclose() raised:", type(exc).__name__, exc)
    else:
        print("B aclose() returned normally -- swallowed")


async def probe_b2() -> None:
    """Same, but the finally awaits first (create_task + shield), then raises."""

    async def gen():
        try:
            yield 1
            yield 2
        finally:
            await asyncio.sleep(0)
            t = asyncio.create_task(asyncio.sleep(0.01))
            await asyncio.shield(t)
            raise ValueError("cleanup failure after awaiting")

    g = gen()
    assert await anext(g) == 1
    try:
        await g.aclose()
    except BaseException as exc:
        print("B2 aclose() raised:", type(exc).__name__, exc)
    else:
        print("B2 aclose() returned normally")


async def probe_b3() -> None:
    """Yield from a finally during aclose -> the classic 'ignored GeneratorExit'."""

    async def gen():
        try:
            yield 1
        finally:
            yield 99

    g = gen()
    await anext(g)
    try:
        await g.aclose()
    except BaseException as exc:
        print("B3 aclose() raised:", type(exc).__name__, exc)
    else:
        print("B3 aclose() returned normally")


async def probe_c() -> None:
    """StopAsyncIteration raised out of an async generator body."""

    async def gen():
        try:
            yield 1
        finally:
            raise StopAsyncIteration

    g = gen()
    await anext(g)
    try:
        await g.aclose()
    except BaseException as exc:
        print("C aclose() raised:", type(exc).__name__, repr(exc))
    else:
        print("C aclose() returned normally")


async def probe_d() -> None:
    """CancelledError as the primary, re-raised from a finally during a plain unwind."""

    async def gen():
        try:
            yield 1
            await asyncio.Event().wait()
        finally:
            print("D sys.exception() in finally:", repr(sys.exception()))

    g = gen()
    await anext(g)

    async def drive():
        async for _ in g:
            pass

    t = asyncio.create_task(drive())
    await asyncio.sleep(0.01)
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        print("D consumer task ended cancelled")


async def main() -> None:
    print("python", sys.version)
    await probe_a()
    await probe_b()
    await probe_b2()
    await probe_b3()
    await probe_c()
    await probe_d()


asyncio.run(main())
