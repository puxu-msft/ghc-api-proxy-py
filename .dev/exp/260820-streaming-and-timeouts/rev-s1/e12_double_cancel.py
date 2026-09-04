"""Cleanup interrupted by repeated cancellation of the closing task."""

import asyncio
import sys
from collections.abc import AsyncIterator

sys.path.insert(0, "/home/xp/src/ghc-api-proxy-py/src")

import orjson

from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import StreamSettings, stream_delivery


def frame(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {orjson.dumps(data).decode()}\n\n".encode()


HEAD = [
    frame("content_block_start", {"index": 0, "content_block": {"type": "text"}}),
    frame("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "hi"}}),
    frame("content_block_stop", {"index": 0}),
]


async def run(cancels: int) -> None:
    log: list[str] = []

    async def raw() -> AsyncIterator[bytes]:
        try:
            for p in HEAD:
                yield p
            await asyncio.Event().wait()
        except BaseException as exc:  # noqa: BLE001
            log.append(f"received:{type(exc).__name__}")
            raise
        finally:
            log.append("closing")
            try:
                await asyncio.shield(asyncio.sleep(0.15))
            except asyncio.CancelledError:
                log.append("close-INTERRUPTED")
                raise
            log.append("closed")

    gen = stream_delivery(
        raw(),
        AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=0.02),  # type: ignore[arg-type]
        message_id="m",
        model="model",
    )

    async def closer() -> None:
        it = gen.__aiter__()
        while True:
            chunk = await asyncio.wait_for(anext(it), 3)
            if chunk == b": ping\n\n":
                break
        await gen.aclose()

    t = asyncio.create_task(closer())
    await asyncio.sleep(0.1)
    for i in range(cancels):
        t.cancel()
        await asyncio.sleep(0.01)
    try:
        await t
        outcome = "returned normally"
    except asyncio.CancelledError:
        outcome = "CancelledError"
    except BaseException as exc:  # noqa: BLE001
        outcome = f"{type(exc).__name__}: {exc}"
    await asyncio.sleep(0.3)
    print(f"cancels={cancels}: closer -> {outcome:16s} upstream={log}")
    assert "close-INTERRUPTED" not in log, "cleanup was interrupted"
    assert "closed" in log


async def main() -> None:
    await run(1)
    await run(2)
    await run(4)


asyncio.run(main())
