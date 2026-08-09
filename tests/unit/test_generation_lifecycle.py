from __future__ import annotations

import asyncio
from typing import cast

import pytest
from uvicorn._types import (
    ASGI3Application,
    ASGIReceiveCallable,
    ASGIReceiveEvent,
    ASGISendCallable,
    ASGISendEvent,
    Scope,
)

from app.generation import (
    GenerationAdmissionMiddleware,
    GenerationLifecycle,
    GenerationLifecycleError,
    GenerationPhase,
)


def _http_scope(path: str = "/v1/messages") -> Scope:
    return cast(
        Scope,
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 4144),
        },
    )


def _websocket_scope() -> Scope:
    return cast(
        Scope,
        {
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": "/v1/responses",
            "raw_path": b"/v1/responses",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 4144),
            "subprotocols": [],
        },
    )


async def _empty_receive() -> ASGIReceiveEvent:
    return {"type": "http.disconnect"}


@pytest.mark.asyncio
async def test_operation_drains_without_premature_standby() -> None:
    lifecycle = GenerationLifecycle()
    await lifecycle.mark_ready()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def app(
        _scope: Scope,
        _receive: ASGIReceiveCallable,
        _send: ASGISendCallable,
    ) -> None:
        entered.set()
        await release.wait()

    async def send(_message: ASGISendEvent) -> None:
        return None

    middleware = GenerationAdmissionMiddleware(cast(ASGI3Application, app), lifecycle)
    operation = asyncio.create_task(middleware(_http_scope(), _empty_receive, send))
    await entered.wait()
    assert lifecycle.active_operations == 1

    await lifecycle.quiesce()
    assert lifecycle.phase is GenerationPhase.QUIESCING
    assert lifecycle.accepting is False
    assert not operation.done()

    release.set()
    await operation
    await lifecycle.wait_for_drained()
    assert lifecycle.active_operations == 0
    assert lifecycle.phase is GenerationPhase.QUIESCING

    await lifecycle.mark_drained()
    assert lifecycle.phase is GenerationPhase.DRAINED_STANDBY
    await lifecycle.resume()
    assert lifecycle.phase is GenerationPhase.READY_ACCEPTING


@pytest.mark.asyncio
async def test_quiescing_rejects_new_http_but_allows_health() -> None:
    lifecycle = GenerationLifecycle()
    await lifecycle.mark_ready()
    await lifecycle.quiesce()
    underlying_calls: list[str] = []
    sent: list[ASGISendEvent] = []

    async def app(
        scope: Scope,
        _receive: ASGIReceiveCallable,
        send: ASGISendCallable,
    ) -> None:
        assert scope["type"] == "http"
        underlying_calls.append(scope["path"])
        await send({"type": "http.response.start", "status": 200})
        await send({"type": "http.response.body", "body": b"ok"})

    async def send(message: ASGISendEvent) -> None:
        sent.append(message)

    middleware = GenerationAdmissionMiddleware(cast(ASGI3Application, app), lifecycle)
    await middleware(_http_scope(), _empty_receive, send)
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 503  # type: ignore[typeddict-item]
    assert (b"connection", b"close") in sent[0]["headers"]  # type: ignore[typeddict-item]
    assert underlying_calls == []

    sent.clear()
    await middleware(_http_scope("/health/liveness"), _empty_receive, send)
    assert sent[0]["status"] == 200  # type: ignore[typeddict-item]
    assert underlying_calls == ["/health/liveness"]


@pytest.mark.asyncio
async def test_quiescing_websocket_accepts_then_closes_1012_without_operation() -> None:
    lifecycle = GenerationLifecycle()
    await lifecycle.mark_ready()
    await lifecycle.quiesce()
    sent: list[ASGISendEvent] = []
    called = False

    async def app(
        _scope: Scope,
        _receive: ASGIReceiveCallable,
        _send: ASGISendCallable,
    ) -> None:
        nonlocal called
        called = True

    async def receive() -> ASGIReceiveEvent:
        return {"type": "websocket.connect"}

    async def send(message: ASGISendEvent) -> None:
        sent.append(message)

    middleware = GenerationAdmissionMiddleware(cast(ASGI3Application, app), lifecycle)
    await middleware(_websocket_scope(), receive, send)

    assert [message["type"] for message in sent] == [
        "websocket.accept",
        "websocket.close",
    ]
    assert sent[1]["code"] == 1012  # type: ignore[typeddict-item]
    assert called is False
    assert lifecycle.active_operations == 0


@pytest.mark.asyncio
async def test_invalid_transitions_fail_closed() -> None:
    lifecycle = GenerationLifecycle()
    with pytest.raises(GenerationLifecycleError, match="quiesce requires"):
        await lifecycle.quiesce()
    with pytest.raises(GenerationLifecycleError, match="resume requires"):
        await lifecycle.resume()
    with pytest.raises(GenerationLifecycleError, match="drained requires"):
        await lifecycle.mark_drained()


@pytest.mark.asyncio
async def test_quiesce_closes_history_and_approval_observers() -> None:
    lifecycle = GenerationLifecycle()
    await lifecycle.mark_ready()

    class Observers:
        closed: set[str] | None = None

        async def close_topics(
            self,
            topics: set[str],
            *,
            code: int,
            reason: str,
        ) -> int:
            assert code == 1012
            assert reason == "server_restarting"
            self.closed = topics
            return 2

        def reopen_topics(self, topics: set[str]) -> None:
            assert topics == {"history", "approval"}
            self.closed = None

    observers = Observers()
    await lifecycle.quiesce(observers=observers)
    assert observers.closed == {"history", "approval"}
    await lifecycle.resume(observers=observers)
    assert observers.closed is None


@pytest.mark.asyncio
async def test_quiesce_cancellation_and_concurrent_resume_converge_consistently() -> None:
    lifecycle = GenerationLifecycle()
    await lifecycle.mark_ready()
    entered = asyncio.Event()
    release = asyncio.Event()

    class Gate:
        open = True

        async def quiesce(self, reason: str = "server_restarting") -> int:
            assert reason == "server_restarting"
            entered.set()
            await release.wait()
            self.open = False
            return 0

        async def resume(self) -> None:
            self.open = True

    gate = Gate()
    quiesce = asyncio.create_task(lifecycle.quiesce(gate))
    await entered.wait()
    assert lifecycle.phase is GenerationPhase.QUIESCING
    assert lifecycle.accepting is False
    resume = asyncio.create_task(lifecycle.resume(gate))
    quiesce.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await quiesce
    await resume
    assert lifecycle.phase is GenerationPhase.READY_ACCEPTING
    assert gate.open is True


@pytest.mark.asyncio
async def test_resume_cancellation_and_stopping_converge_to_stopping() -> None:
    lifecycle = GenerationLifecycle()
    await lifecycle.mark_ready()
    await lifecycle.quiesce()
    entered = asyncio.Event()
    release = asyncio.Event()

    class Gate:
        async def quiesce(self, reason: str = "server_restarting") -> int:
            del reason
            return 0

        async def resume(self) -> None:
            entered.set()
            await release.wait()

    gate = Gate()
    resume = asyncio.create_task(lifecycle.resume(gate))
    await entered.wait()
    stopping = asyncio.create_task(lifecycle.start_stopping())
    resume.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await resume
    await stopping
    assert lifecycle.phase is GenerationPhase.STOPPING
    assert lifecycle.accepting is False


@pytest.mark.asyncio
async def test_atomic_admission_permit_has_only_accept_or_reject_outcomes() -> None:
    lifecycle = GenerationLifecycle()
    await lifecycle.mark_ready()
    async with lifecycle.try_admit() as admitted:
        assert admitted is True
        await lifecycle.quiesce()
        assert lifecycle.active_operations == 1
    await lifecycle.wait_for_drained()
    async with lifecycle.try_admit() as admitted:
        assert admitted is False


@pytest.mark.asyncio
async def test_outer_wrapper_holds_operation_through_error_response_send() -> None:
    lifecycle = GenerationLifecycle()
    await lifecycle.mark_ready()
    counts: list[int] = []

    async def inner(
        _scope: Scope,
        _receive: ASGIReceiveCallable,
        send: ASGISendCallable,
    ) -> None:
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            counts.append(lifecycle.active_operations)
            await send({"type": "http.response.start", "status": 500})
            counts.append(lifecycle.active_operations)
            await send({"type": "http.response.body", "body": b"error"})
            counts.append(lifecycle.active_operations)

    async def send(_message: ASGISendEvent) -> None:
        counts.append(lifecycle.active_operations)

    middleware = GenerationAdmissionMiddleware(cast(ASGI3Application, inner), lifecycle)
    await middleware(_http_scope(), _empty_receive, send)

    assert counts and all(count == 1 for count in counts)
    assert lifecycle.active_operations == 0
