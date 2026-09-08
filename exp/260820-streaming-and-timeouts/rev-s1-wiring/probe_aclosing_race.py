"""Probe G: minimal reproduction of the stderr noise the `aclosing` wrapper introduces.

No project code. Two generators, one abandoned at a `yield`, then collected — with and without
an `aclosing` around the inner one.
"""

import asyncio
import gc
from collections.abc import AsyncGenerator
from contextlib import aclosing

ERRORS: list[str] = []


async def inner() -> AsyncGenerator[int]:
    try:
        for value in (1, 2, 3):
            yield value
    finally:
        await asyncio.sleep(0)


async def middle_bare() -> AsyncGenerator[int]:
    it = inner()
    async for value in it:
        yield value


async def middle_closing() -> AsyncGenerator[int]:
    src = inner()
    close = src.aclose
    try:
        async for value in src:
            yield value
    finally:
        await close()


async def outer_bare() -> AsyncGenerator[int]:
    it = middle_bare()
    async for value in it:
        yield value


async def outer_aclosing() -> AsyncGenerator[int]:
    async with aclosing(middle_closing()) as it:
        async for value in it:
            yield value


async def run(label: str, factory) -> None:  # noqa: ANN001
    ERRORS.clear()
    gen = factory()
    async for _ in gen:
        break
    # Abandoned at a yield and dropped, exactly as Starlette drops `body_iterator`.
    del gen
    for _ in range(3):
        gc.collect()
        await asyncio.sleep(0.05)
    print(f"  {label:<16} stderr errors: {ERRORS or 'none'}", flush=True)


def handler(loop, context) -> None:  # noqa: ANN001
    ERRORS.append(str(context.get("exception") or context.get("message")))


async def main() -> None:
    asyncio.get_running_loop().set_exception_handler(handler)
    for _ in range(3):
        await run("all bare (before)", outer_bare)
        await run("aclosing chain (after)", outer_aclosing)


if __name__ == "__main__":
    asyncio.run(main())
