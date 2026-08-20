"""Probe D: does anything a client can see change?

Four classes of request driven through the real `stream_delivery`, dumping the exact bytes the
client would receive plus what the caller ends up raising. Run against both trees and diff.

    success            upstream finishes with message_stop
    upstream-error     upstream raises mid-stream (httpx.ReadError is what a dropped TCP read is)
    upstream-timeout   upstream raises StreamIdleTimeoutError, the project's own idle timeout
    truncated          upstream just stops, no terminal event
    ping               a long gap with a keep-alive interval set, so the None branch runs
    synth-preamble     synthesized_response_headers_after_sec fires before the first block

Plus the two disconnect shapes:
    abandon-at-yield   consumer stops while the delivery is suspended at a `yield`
    abandon-at-pull    consumer stops while the delivery is waiting on upstream
"""

import asyncio
import sys
from collections.abc import AsyncIterator
from typing import Any

import orjson

from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import StreamSettings, stream_delivery
from app.streaming.idle_timeout import StreamIdleTimeoutError


def frame(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {orjson.dumps(data).decode()}\n\n".encode()


def anthropic_stream(*texts: str) -> list[bytes]:
    chunks: list[bytes] = []
    for index, text in enumerate(texts):
        chunks.append(frame("content_block_start", {"index": index, "content_block": {"type": "text"}}))
        chunks.append(frame("content_block_delta", {"index": index, "delta": {"type": "text_delta", "text": text}}))
        chunks.append(frame("content_block_stop", {"index": index}))
    chunks.append(frame("message_delta", {"delta": {"stop_reason": "end_turn"}}))
    chunks.append(frame("message_stop", {}))
    return chunks


CLOSED: list[str] = []


async def feed(payloads: list[bytes], *, gap: float = 0.0, raises: BaseException | None = None, tag: str = "") -> AsyncIterator[bytes]:
    try:
        for payload in payloads:
            if gap:
                await asyncio.sleep(gap)
            yield payload
        if raises is not None:
            raise raises
    finally:
        CLOSED.append(tag)


def delivery(chunks: AsyncIterator[bytes], *, interval: int = 0, synth: int = 0, policy: str = "block") -> Any:
    return stream_delivery(
        chunks,
        AnthropicAssembler(),
        buffer=BlockBuffer(policy=policy),
        settings=StreamSettings(sse_ping_interval=interval, synthesized_response_headers_after_sec=synth),
        message_id="msg_probe",
        model="test-model",
    )


async def drain(name: str, gen: Any, *, stop_after: int | None = None) -> None:
    CLOSED.clear()
    out: list[bytes] = []
    error = "none"
    try:
        async for chunk in gen:
            out.append(chunk)
            if stop_after is not None and len(out) >= stop_after:
                break
        else:
            pass
    except BaseException as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    if stop_after is not None:
        try:
            await gen.aclose()
        except BaseException as exc:  # noqa: BLE001
            error = f"aclose -> {type(exc).__name__}: {exc}"
    print(f"--- {name}")
    print(f"    raised            : {error}")
    print(f"    upstream_closed   : {CLOSED}")
    print(f"    chunks            : {len(out)}")
    for chunk in out:
        print(f"      {chunk!r}")


async def main() -> None:
    import app.pipeline.delivery.stream as m

    print(f"stream.py under test: {m.__file__}\n")

    await drain("success", delivery(feed(anthropic_stream("one", "two"), tag="success")))
    await drain(
        "upstream-error",
        delivery(feed(anthropic_stream("one")[:3], raises=RuntimeError("upstream read failed"), tag="err")),
    )
    await drain(
        "upstream-timeout",
        delivery(feed(anthropic_stream("one")[:3], raises=StreamIdleTimeoutError("No upstream stream item received for 60s"), tag="timeout")),
    )
    await drain("truncated", delivery(feed(anthropic_stream("one")[:3], tag="trunc")))
    await drain("ping", delivery(feed(anthropic_stream("one"), gap=0.03, tag="ping"), interval=1))
    await drain("synth-preamble", delivery(feed(anthropic_stream("one"), gap=0.05, tag="synth"), interval=1, synth=1))
    await drain("abandon-at-yield", delivery(feed(anthropic_stream("one", "two"), tag="aband-y")), stop_after=1)

    # A consumer that walks away while the delivery is still waiting on upstream.
    async def hanging() -> AsyncIterator[bytes]:
        try:
            for payload in anthropic_stream("one")[:3]:
                yield payload
            await asyncio.Event().wait()
        finally:
            CLOSED.append("aband-p")

    CLOSED.clear()
    gen = delivery(hanging())
    out: list[bytes] = []
    pump_error = "none"

    async def pump() -> None:
        async for chunk in gen:
            out.append(chunk)

    task = asyncio.create_task(pump())
    await asyncio.sleep(0.15)
    task.cancel()
    try:
        await task
    except BaseException as exc:  # noqa: BLE001
        pump_error = type(exc).__name__
    try:
        await gen.aclose()
    except BaseException as exc:  # noqa: BLE001
        pump_error += f" / aclose -> {type(exc).__name__}: {exc}"
    live = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    print("--- abandon-at-pull")
    print(f"    raised            : {pump_error}")
    print(f"    upstream_closed   : {CLOSED}")
    print(f"    leftover tasks    : {len(live)}")
    print(f"    chunks            : {len(out)}")
    for chunk in out:
        print(f"      {chunk!r}")

    sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(main())
