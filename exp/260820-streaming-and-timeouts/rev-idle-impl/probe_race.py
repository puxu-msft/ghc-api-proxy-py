"""Does an external cancellation arriving inside `anyio.fail_after` get reported as an idle timeout?

If anyio's scope swallows a cancellation it did not cause, a client disconnect that races the deadline is logged as `fail: No stream item received` instead of `gone`.
"""
import asyncio
from collections.abc import AsyncIterator

from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import StreamSettings, stream_delivery
from app.streaming.idle_timeout import StreamIdleTimeoutError, with_idle_timeout

FRAMES = [
    b'event: content_block_start\ndata: {"index":0,"content_block":{"type":"text"}}\n\n',
    b'event: content_block_delta\ndata: {"index":0,"delta":{"type":"text_delta","text":"one"}}\n\n',
    b'event: content_block_stop\ndata: {"index":0}\n\n',
]


async def quiet(reached: asyncio.Event) -> AsyncIterator[bytes]:
    for f in FRAMES:
        yield f
    reached.set()
    await asyncio.Event().wait()


async def once(cancel_at: float, timeout: float) -> str:
    reached = asyncio.Event()
    d = stream_delivery(
        with_idle_timeout(quiet(reached), timeout_seconds=timeout),
        AnthropicAssembler(), buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=0), message_id="m", model="model",
    )
    seen: list[str] = []

    async def pump():
        try:
            async for _ in d:
                pass
        except BaseException as exc:
            seen.append(type(exc).__name__)
            raise

    task = asyncio.create_task(pump())
    await asyncio.wait_for(reached.wait(), 2)
    await asyncio.sleep(cancel_at)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        seen.append("outer:CancelledError")
    except StreamIdleTimeoutError:
        seen.append("outer:StreamIdleTimeoutError")
    except BaseException as exc:
        seen.append(f"outer:{type(exc).__name__}")
    try:
        await d.aclose()
    except BaseException as exc:
        seen.append(f"aclose:{type(exc).__name__}")
    return ",".join(seen)


async def main():
    T = 0.30
    print(f"guard timeout = {T}s; cancelling the pump at offsets around the deadline")
    for offset in (0.0, 0.10, 0.20, 0.28, 0.295, 0.2995, 0.2999, 0.30, 0.3001, 0.31, 0.40):
        try:
            r = await asyncio.wait_for(once(offset, T), 5)
        except TimeoutError:
            r = "HUNG"
        print(f"  cancel at t+{offset:<7.4f} -> {r}")


asyncio.run(main())
