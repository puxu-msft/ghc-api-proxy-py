"""Nesting semantics of the two driver guards, reproduced in isolation."""

import asyncio
import sys

sys.path.insert(0, "/tmp/rev-tw/snap/src")

from app.pipeline.exceptions import UpstreamTimeout, classify  # noqa: E402
from app.pipeline.retry import reason_for  # noqa: E402


async def guarded(*, header: float, deadline: float, upstream_delay: float) -> str:
    """The exact shape of base.py:_send, with the send replaced by a sleep."""

    async def send() -> str:
        await asyncio.sleep(upstream_delay)
        return "response"

    coro = send()

    async def under_header_guard() -> str:
        if header <= 0:
            return await coro
        try:
            async with asyncio.timeout(header):
                return await coro
        except TimeoutError as error:
            raise UpstreamTimeout(f"no response headers within {header}s") from error

    deadline_at = asyncio.get_running_loop().time() + deadline if deadline > 0 else None
    if deadline_at is None:
        return await under_header_guard()
    try:
        async with asyncio.timeout_at(deadline_at):
            return await under_header_guard()
    except TimeoutError as error:
        raise UpstreamTimeout(f"attempt exceeded {deadline}s") from error


async def report(label: str, **kw: float) -> None:
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    try:
        out = await guarded(**kw)
        print(f"{label}: OK {out!r} after {loop.time() - t0:.3f}s")
    except BaseException as exc:  # noqa: BLE001
        print(
            f"{label}: {type(exc).__name__}: {exc} after {loop.time() - t0:.3f}s"
            f" | classify={classify(exc)} reason={reason_for(exc)}"
            f" | chain={[type(e).__name__ for e in _chain(exc)]}"
        )


def _chain(exc: BaseException) -> list[BaseException]:
    seen: list[BaseException] = []
    cur: BaseException | None = exc
    while cur is not None and cur not in seen:
        seen.append(cur)
        cur = cur.__cause__ or cur.__context__
    return seen


async def main() -> None:
    print("--- 1. header shorter, header should win ---")
    await report("header=1 deadline=10 delay=5", header=1, deadline=10, upstream_delay=5)

    print("--- 2. deadline shorter, deadline should win ---")
    await report("header=10 deadline=1 delay=5", header=10, deadline=1, upstream_delay=5)

    print("--- 3. contradictory: header LONGER than deadline ---")
    await report("header=30 deadline=2 delay=60", header=30, deadline=2, upstream_delay=60)

    print("--- 4. exactly equal ---")
    for i in range(5):
        await report(f"equal run {i}", header=0.5, deadline=0.5, upstream_delay=5)

    print("--- 5. near-equal, header a hair shorter ---")
    await report("header=0.5 deadline=0.5001", header=0.5, deadline=0.5001, upstream_delay=5)
    print("--- 6. near-equal, deadline a hair shorter ---")
    await report("header=0.5001 deadline=0.5", header=0.5001, deadline=0.5, upstream_delay=5)

    print("--- 7. neither fires ---")
    await report("header=5 deadline=5 delay=0.05", header=5, deadline=5, upstream_delay=0.05)

    print("--- 8. header disabled, deadline fires ---")
    await report("header=0 deadline=1 delay=5", header=0, deadline=1, upstream_delay=5)

    print("--- 9. deadline disabled, header fires ---")
    await report("header=1 deadline=0 delay=5", header=1, deadline=0, upstream_delay=5)

    print("--- 10. is UpstreamTimeout a TimeoutError? ---")
    print("issubclass:", issubclass(UpstreamTimeout, TimeoutError))
    print("mro:", [c.__name__ for c in UpstreamTimeout.__mro__])


asyncio.run(main())
