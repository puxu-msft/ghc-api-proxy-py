"""Probe H: the contract of `_AccountedStreamingResponse.__call__`'s finally.

The landed fix put an `await` in front of `self._accounting.finish()`. An `await` in a `finally`
can be preempted and can raise, and either would cost the request its footer slot and its
completion line. This drives the real class with a controllable body through every shape that
finally has to survive.

Run against both `v2-<stamp>-nofix` and `v2-<stamp>-fix` and diff.
"""

import asyncio
import sys
import time
from collections.abc import AsyncGenerator
from typing import Any

import app.server.pipeline_app as pa
from app.observability.active_requests import ActiveRequestRegistry
from app.pipeline.delivery.assembler import AnthropicAssembler

LOGGED: list[dict[str, Any]] = []


def fake_log_completion(chain: Any, trace: Any, status_code: int | None, *, bytes_out: int | None) -> None:
    LOGGED.append({"status": status_code, "bytes_out": bytes_out, "detail": trace.detail, "failed": getattr(trace, "failed", None)})


pa._log_completion = fake_log_completion  # noqa: SLF001


class FakeCapabilities:
    unicode = False
    color = False


class FakeChain:
    def __init__(self) -> None:
        self.active_requests = ActiveRequestRegistry()
        self.capabilities = FakeCapabilities()


SCOPE = {
    "type": "http",
    "asgi": {"version": "3.0", "spec_version": "2.3"},
    "method": "POST",
    "path": "/v1/messages",
    "headers": [],
    "http_version": "1.1",
}


def build(content: AsyncGenerator[bytes]) -> tuple[Any, Any, Any]:
    chain = FakeChain()
    trace = pa._Trace(method="POST", path="/v1/messages", request_id="rid", started=time.monotonic())  # noqa: SLF001
    chain.active_requests.add("rid")
    accounting = pa._StreamAccounting(  # noqa: SLF001
        chain=chain, request_id="rid", trace=trace, status_code=200, context=None, assembler=AnthropicAssembler()
    )
    response = pa._AccountedStreamingResponse(content, accounting, status_code=200, media_type="text/event-stream")  # noqa: SLF001
    return response, accounting, chain


async def report(name: str, response: Any, accounting: Any, chain: Any, *, coro) -> None:  # noqa: ANN001
    LOGGED.clear()
    raised = "none"
    try:
        await coro
    except BaseException as exc:  # noqa: BLE001
        raised = f"{type(exc).__name__}: {exc}"
    print(
        f"  {name:<28} raised={raised:<44} finish_done={accounting.done!s:<5} "
        f"log_lines={len(LOGGED)} footer={[r.request_id for r in chain.active_requests.snapshot()]}",
        flush=True,
    )


CLEANUP: list[str] = []


async def plain_body() -> AsyncGenerator[bytes]:
    try:
        yield b"a"
        yield b"b"
    finally:
        CLEANUP.append("plain")


async def raising_body() -> AsyncGenerator[bytes]:
    try:
        yield b"a"
        raise RuntimeError("upstream read failed")
    finally:
        CLEANUP.append("raising")


async def bad_cleanup_body() -> AsyncGenerator[bytes]:
    try:
        yield b"a"
        yield b"b"
    finally:
        CLEANUP.append("bad")
        raise ValueError("cleanup blew up")


async def hanging_body() -> AsyncGenerator[bytes]:
    try:
        yield b"a"
        await asyncio.Event().wait()
    finally:
        CLEANUP.append("hanging")


async def ok_send(message: dict[str, Any]) -> None:
    return None


async def never_receive() -> dict[str, Any]:
    await asyncio.Event().wait()
    return {"type": "http.disconnect"}


async def main() -> None:
    print(f"pipeline_app under test: {pa.__file__}\n", flush=True)

    # 1. Ordinary success: the body runs out on its own.
    CLEANUP.clear()
    response, accounting, chain = build(plain_body())
    await report("success", response, accounting, chain, coro=response(SCOPE, never_receive, ok_send))
    print(f"      body cleanup ran: {CLEANUP}", flush=True)

    # 2. `http.response.start` fails: the body is never iterated at all.
    async def failing_start(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            raise OSError("client vanished before the headers went out")

    CLEANUP.clear()
    response, accounting, chain = build(plain_body())
    await report("start-send-fails", response, accounting, chain, coro=response(SCOPE, never_receive, failing_start))
    print(f"      body cleanup ran: {CLEANUP}  (empty is correct: never iterated)", flush=True)

    # 3. The body raises mid-stream.
    CLEANUP.clear()
    response, accounting, chain = build(raising_body())
    await report("body-raises", response, accounting, chain, coro=response(SCOPE, never_receive, ok_send))
    print(f"      body cleanup ran: {CLEANUP}", flush=True)

    # 4. The body's own cleanup raises when it is closed.
    CLEANUP.clear()
    response, accounting, chain = build(bad_cleanup_body())

    async def disconnect_after_first(message: dict[str, Any]) -> None:
        return None

    sent = asyncio.Event()

    async def send_then_stop(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.body" and message.get("body"):
            sent.set()
            await asyncio.sleep(5)

    async def receive_disconnect() -> dict[str, Any]:
        await sent.wait()
        return {"type": "http.disconnect"}

    await report("cleanup-raises-on-close", response, accounting, chain, coro=response(SCOPE, receive_disconnect, send_then_stop))
    print(f"      body cleanup ran: {CLEANUP}", flush=True)

    # 5. The whole `__call__` is cancelled from outside — server shutdown, or an outer scope.
    CLEANUP.clear()
    response, accounting, chain = build(hanging_body())
    task = asyncio.create_task(response(SCOPE, never_receive, ok_send))
    await asyncio.sleep(0.1)
    task.cancel()
    await report("call-cancelled", response, accounting, chain, coro=task)
    print(f"      body cleanup ran: {CLEANUP}", flush=True)

    # 6. Cancelled twice, the way an anyio cancel scope re-delivers at every checkpoint.
    CLEANUP.clear()
    response, accounting, chain = build(hanging_body())
    task = asyncio.create_task(response(SCOPE, never_receive, ok_send))
    await asyncio.sleep(0.1)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await report("call-cancelled-twice", response, accounting, chain, coro=task)
    print(f"      body cleanup ran: {CLEANUP}", flush=True)

    # 6b. Both at once: the framework raises AND the body's cleanup raises. Which one reaches the server?
    CLEANUP.clear()
    response, accounting, chain = build(bad_cleanup_body())

    async def start_ok_body_fails(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.body" and message.get("body"):
            raise OSError("broken pipe")

    await report("primary+cleanup-both-raise", response, accounting, chain, coro=response(SCOPE, never_receive, start_ok_body_fails))
    print(f"      body cleanup ran: {CLEANUP}", flush=True)

    # 7. `finish()` really is idempotent: call it again by hand.
    LOGGED.clear()
    response, accounting, chain = build(plain_body())
    await response(SCOPE, never_receive, ok_send)
    before = len(LOGGED)
    accounting.finish()
    accounting.finish()
    print(f"  {'finish-idempotent':<28} log lines after 2 extra finish(): {before} -> {len(LOGGED)}", flush=True)

    sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(main())
