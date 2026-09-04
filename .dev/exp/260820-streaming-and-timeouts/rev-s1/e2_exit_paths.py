"""Exit-path enumeration for _events_with_ping / stream_delivery.

Records, for each way out, what the upstream byte source actually received.
"""

import asyncio
import sys
from collections.abc import AsyncIterator

sys.path.insert(0, "/home/xp/src/ghc-api-proxy-py/src")
sys.path.insert(0, "/home/xp/src/ghc-api-proxy-py/tests")

import orjson

from app.pipeline.delivery.assembler import AnthropicAssembler
from app.pipeline.delivery.blocks import BlockBuffer
from app.pipeline.delivery.stream import StreamSettings, stream_delivery


def frame(event: str, data: dict) -> bytes:
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


class Log:
    def __init__(self) -> None:
        self.events: list[str] = []

    def add(self, what: str) -> None:
        self.events.append(what)

    def __repr__(self) -> str:
        return repr(self.events)


def upstream(
    log: Log,
    payloads: list[bytes],
    *,
    gap: float = 0.0,
    hang_after: int | None = None,
    raise_after: int | None = None,
    error: BaseException | None = None,
) -> AsyncIterator[bytes]:
    async def gen() -> AsyncIterator[bytes]:
        sent = 0
        try:
            for payload in payloads:
                if gap:
                    await asyncio.sleep(gap)
                yield payload
                sent += 1
                if raise_after is not None and sent == raise_after:
                    log.add("raising")
                    raise error or RuntimeError("upstream blew up")
                if hang_after is not None and sent == hang_after:
                    log.add("hanging")
                    await asyncio.Event().wait()
            log.add("exhausted")
        except BaseException as exc:  # noqa: BLE001
            log.add(f"received:{type(exc).__name__}")
            raise
        finally:
            log.add("closed")

    return gen()


def delivery(chunks: AsyncIterator[bytes], *, interval: int = 0):
    return stream_delivery(
        chunks,
        AnthropicAssembler(),
        buffer=BlockBuffer(policy="block"),
        settings=StreamSettings(sse_ping_interval=interval),
        message_id="m",
        model="model",
    )


def task_snapshot() -> set:
    return {t for t in asyncio.all_tasks() if t is not asyncio.current_task()}


async def case(name: str, body) -> None:
    before = task_snapshot()
    log = Log()
    outcome = "ok"
    try:
        await body(log)
    except BaseException as exc:  # noqa: BLE001
        outcome = f"raised {type(exc).__name__}: {exc}"
    await asyncio.sleep(0)
    leaked = task_snapshot() - before
    print(f"{name:38s} upstream={log!r:60s} out={outcome:32s} leaked_tasks={len(leaked)}")
    for t in leaked:
        print("        leaked:", t)
        t.cancel()


# ---------------------------------------------------------------- exit paths

async def c_normal(log: Log) -> None:
    d = delivery(upstream(log, anthropic_stream("a", "b")))
    async for _ in d:
        pass


async def c_normal_with_ping(log: Log) -> None:
    d = delivery(upstream(log, anthropic_stream("a", "b"), gap=0.03), interval=1)
    # interval in seconds is an int; force pings by using a tiny interval via monkeyed settings
    async for _ in d:
        pass


async def c_upstream_error(log: Log) -> None:
    d = delivery(upstream(log, anthropic_stream("a", "b"), raise_after=3))
    async for _ in d:
        pass


async def c_upstream_idle_timeout(log: Log) -> None:
    from app.streaming.idle_timeout import StreamIdleTimeoutError

    d = delivery(upstream(log, anthropic_stream("a", "b"), raise_after=3, error=StreamIdleTimeoutError("idle")))
    async for _ in d:
        pass


async def c_consumer_aclose(log: Log) -> None:
    d = delivery(upstream(log, anthropic_stream("a", "b")))
    async for _ in d:
        break
    await d.aclose()


async def c_consumer_aclose_midpull(log: Log) -> None:
    reached = asyncio.Event()

    async def src() -> AsyncIterator[bytes]:
        try:
            for payload in anthropic_stream("a")[:3]:
                yield payload
            reached.set()
            await asyncio.Event().wait()
        except BaseException as exc:  # noqa: BLE001
            log.add(f"received:{type(exc).__name__}")
            raise
        finally:
            log.add("closed")

    d = delivery(src())
    pump = asyncio.create_task(_drain(d))
    await asyncio.wait_for(reached.wait(), 2)
    await asyncio.sleep(0.02)
    pump.cancel()
    try:
        await pump
    except asyncio.CancelledError:
        pass
    await d.aclose()


async def _drain(d) -> None:
    async for _ in d:
        pass


async def c_consumer_task_cancelled_in_pull(log: Log) -> None:
    """Cancelled while the consumer is blocked inside anext -- the Esc-while-thinking case."""
    reached = asyncio.Event()

    async def src() -> AsyncIterator[bytes]:
        try:
            for payload in anthropic_stream("a")[:3]:
                yield payload
            reached.set()
            await asyncio.Event().wait()
        except BaseException as exc:  # noqa: BLE001
            log.add(f"received:{type(exc).__name__}")
            raise
        finally:
            log.add("closed")

    d = delivery(src())
    pump = asyncio.create_task(_drain(d))
    await asyncio.wait_for(reached.wait(), 2)
    await asyncio.sleep(0.02)
    pump.cancel()
    try:
        await pump
    except asyncio.CancelledError:
        pass
    # deliberately NOT calling aclose(): this is what starlette does today
    del d
    import gc

    gc.collect()
    await asyncio.sleep(0.05)


async def c_cancel_during_cleanup(log: Log) -> None:
    """Cancel the consumer task again while finish_stream_cleanup is running."""
    reached = asyncio.Event()
    slow_close = asyncio.Event()

    async def src() -> AsyncIterator[bytes]:
        try:
            for payload in anthropic_stream("a")[:3]:
                yield payload
            reached.set()
            await asyncio.Event().wait()
        except BaseException as exc:  # noqa: BLE001
            log.add(f"received:{type(exc).__name__}")
            raise
        finally:
            log.add("closing-slowly")
            try:
                await asyncio.shield(_sleep(0.2))
            except asyncio.CancelledError:
                log.add("close-interrupted")
                raise
            log.add("closed")
            slow_close.set()

    d = delivery(src())

    async def closer() -> None:
        async for _ in d:
            break
        await d.aclose()

    t = asyncio.create_task(closer())
    await asyncio.sleep(0.02)
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        log.add("closer-cancelled")
    await asyncio.sleep(0.3)


async def _sleep(s: float) -> None:
    await asyncio.sleep(s)


async def main() -> None:
    await case("normal end", c_normal)
    await case("upstream raises", c_upstream_error)
    await case("upstream StreamIdleTimeoutError", c_upstream_idle_timeout)
    await case("consumer aclose (idle)", c_consumer_aclose)
    await case("consumer aclose (pull in flight)", c_consumer_aclose_midpull)
    await case("consumer task cancelled in pull", c_consumer_task_cancelled_in_pull)
    await case("cancelled during cleanup", c_cancel_during_cleanup)


asyncio.run(main())
