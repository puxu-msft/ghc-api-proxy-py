"""(b) Does plan B false-kill an upstream that keeps the connection alive with SSE comments?

Both plans get the same two upstreams and the same 1s budget.

  C1  upstream emits `: ping\n\n` every 0.6s for 2.4s, then finishes the turn properly.
      Bytes are flowing the whole time. Parsed events in that window: zero.
  C2  upstream says nothing at all for 2.4s, then finishes the turn properly.

Correct behaviour under the frozen invariant: C1 delivered whole, C2 given up on.
"""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator

from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import StreamSettings, stream_delivery
from app.streaming.idle_timeout import StreamIdleTimeoutError, with_idle_timeout

HEAD = (
    b'event: message_start\ndata: {"message":{"id":"msg_1","usage":{}}}\n\n'
    b'event: content_block_start\ndata: {"index":0,"content_block":{"type":"text","text":""}}\n\n'
    b'event: content_block_delta\ndata: {"index":0,"delta":{"type":"text_delta","text":"hi"}}\n\n'
    b'event: content_block_stop\ndata: {"index":0}\n\n'
)
TAIL = (
    b'event: message_delta\ndata: {"delta":{"stop_reason":"end_turn"}}\n\n'
    b"event: message_stop\ndata: {}\n\n"
)

GAP = 2.4
IDLE = 1.0


async def upstream_with_comment_keepalive() -> AsyncGenerator[bytes]:
    yield HEAD
    elapsed = 0.0
    while elapsed < GAP:
        await asyncio.sleep(0.6)
        elapsed += 0.6
        yield b": ping\n\n"  # bytes on the wire; no parsed event
    yield TAIL


async def upstream_trickling_one_big_frame() -> AsyncGenerator[bytes]:
    """C3: one legitimately large block, arriving in pieces. Bytes flow; no frame completes."""
    yield HEAD
    big = b'event: content_block_start\ndata: {"index":1,"content_block":{"type":"tool_use","input":{"x":"'
    yield big
    for _ in range(4):
        await asyncio.sleep(0.6)
        yield b"A" * 4096          # still inside the same frame
    yield b'"}}}\n\n'
    yield b'event: content_block_stop\ndata: {"index":1}\n\n'
    yield TAIL


async def upstream_that_is_truly_silent() -> AsyncGenerator[bytes]:
    yield HEAD
    await asyncio.sleep(GAP)
    yield TAIL


def deliver(chunks: AsyncIterator[bytes], *, plan_b_idle: float) -> AsyncGenerator[bytes]:
    return stream_delivery(
        chunks,
        AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=0, upstream_idle_seconds=plan_b_idle),
        message_id="msg_1",
        model="claude-model",
    )


async def run(plan: str, upstream: AsyncGenerator[bytes]) -> str:
    if plan == "A":
        delivery = deliver(with_idle_timeout(upstream, timeout_seconds=IDLE), plan_b_idle=0.0)
    else:
        delivery = deliver(upstream, plan_b_idle=IDLE)
    body = b""
    try:
        async with asyncio.timeout(20):
            async for chunk in delivery:
                body += chunk
    except StreamIdleTimeoutError as error:
        return f"FIRED  ({error})"
    finally:
        await delivery.aclose()
    whole = b'"text":"hi"' in body and b"message_stop" in body
    return "delivered whole" if whole else f"delivered PARTIAL: {body[:80]!r}"


async def main() -> None:
    cases = (
        ("C1 comment keepalive every 0.6s over 2.4s", upstream_with_comment_keepalive),
        ("C2 真静默 2.4s                            ", upstream_that_is_truly_silent),
        ("C3 一个大 frame 分片 trickle 2.4s          ", upstream_trickling_one_big_frame),
    )
    print(f"idle budget = {IDLE}s, quiet window = {GAP}s\n")
    for plan in ("A", "B"):
        for label, build in cases:
            print(f"  plan {plan}  {label} -> {await run(plan, build())}")
        print()


asyncio.run(main())
