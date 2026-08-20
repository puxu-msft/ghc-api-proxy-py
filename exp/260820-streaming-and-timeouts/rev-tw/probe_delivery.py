"""Behaviour of app.streaming.deadline.with_deadline_at, on the snapshot copy."""

import asyncio
import sys

sys.path.insert(0, "/tmp/rev-tw/snap/src")

from app.streaming.deadline import StreamDeadlineError, with_deadline_at  # noqa: E402
from app.streaming.idle_timeout import StreamIdleTimeoutError, with_idle_timeout  # noqa: E402


class Source:
    """An async iterator that records whether it was closed."""

    def __init__(self, gaps: list[float], *, tail_sleep: float | None = None) -> None:
        self.gaps = gaps
        self.tail_sleep = tail_sleep
        self.closed = False
        self.produced = 0

    def __aiter__(self) -> "Source":
        return self

    async def __anext__(self) -> int:
        if self.produced < len(self.gaps):
            await asyncio.sleep(self.gaps[self.produced])
            self.produced += 1
            return self.produced
        if self.tail_sleep is not None:
            await asyncio.sleep(self.tail_sleep)
        raise StopAsyncIteration

    async def aclose(self) -> None:
        self.closed = True


async def case(label: str, coro):  # noqa: ANN001
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    try:
        result = await coro
        print(f"{label}: OK {result} after {loop.time() - t0:.3f}s")
    except BaseException as exc:  # noqa: BLE001
        print(f"{label}: {type(exc).__name__}: {exc} after {loop.time() - t0:.3f}s")


async def drain(it) -> list[int]:  # noqa: ANN001
    return [x async for x in it]


async def main() -> None:
    loop = asyncio.get_running_loop()

    print("--- A. inner idle guard fires first: whose name comes out? ---")
    src = Source([0.0, 0.0], tail_sleep=10)
    await case(
        "idle=0.3 deadline=+30",
        drain(with_deadline_at(with_idle_timeout(src, timeout_seconds=0.3), loop.time() + 30)),
    )
    print("   source closed:", src.closed)

    print("--- B. outer deadline fires first, inner idle generous ---")
    src = Source([0.0, 0.0], tail_sleep=10)
    await case(
        "idle=30 deadline=+0.3",
        drain(with_deadline_at(with_idle_timeout(src, timeout_seconds=30), loop.time() + 0.3)),
    )
    print("   source closed:", src.closed)

    print("--- C. both very close (idle 0.30 vs deadline 0.31) x5 ---")
    for i in range(5):
        src = Source([0.0], tail_sleep=10)
        await case(
            f"   run {i}",
            drain(with_deadline_at(with_idle_timeout(src, timeout_seconds=0.30), loop.time() + 0.31)),
        )

    print("--- D. deadline already in the past ---")
    src = Source([0.0, 0.0, 0.0])
    await case("past deadline, source ready immediately", drain(with_deadline_at(src, loop.time() - 5)))
    print("   source closed:", src.closed, "produced:", src.produced)

    print("--- D2. deadline in the past, source that awaits ---")
    src = Source([0.01, 0.01, 0.01])
    await case("past deadline, source sleeps", drain(with_deadline_at(src, loop.time() - 5)))
    print("   source closed:", src.closed, "produced:", src.produced)

    print("--- E. deadline None: nothing bounds it ---")
    src = Source([0.05, 0.05, 0.05])
    await case("None", drain(with_deadline_at(src, None)))
    print("   source closed:", src.closed)

    print("--- F. slow consumer: is time between pulls counted? ---")
    src = Source([0.0] * 10)
    gen = with_deadline_at(src, loop.time() + 0.5)
    got = 0
    try:
        async for _ in gen:
            got += 1
            await asyncio.sleep(0.2)  # consumer holds the generator suspended
    except BaseException as exc:  # noqa: BLE001
        print(f"   consumer-side: {type(exc).__name__}: {exc}; items={got}")
    else:
        print(f"   drained fully; items={got}")
    print("   source closed:", src.closed)

    print("--- G. consumer abandons the generator: is the source closed? ---")
    src = Source([0.0] * 10)
    gen = with_deadline_at(src, loop.time() + 30)
    print("   first item:", await anext(gen))
    await gen.aclose()
    print("   source closed after gen.aclose():", src.closed)

    print("--- H. consumer task cancelled mid-pull ---")
    src = Source([5.0])
    gen = with_deadline_at(src, loop.time() + 30)
    task = asyncio.create_task(drain(gen))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        print("   task cancelled as expected")
    await asyncio.sleep(0)
    print("   source closed:", src.closed)

    print("--- I. exception classes ---")
    print("   StreamDeadlineError is TimeoutError:", issubclass(StreamDeadlineError, TimeoutError))
    print("   StreamIdleTimeoutError is TimeoutError:", issubclass(StreamIdleTimeoutError, TimeoutError))
    print("   StreamDeadlineError catches StreamIdleTimeoutError:", issubclass(StreamIdleTimeoutError, StreamDeadlineError))


asyncio.run(main())
