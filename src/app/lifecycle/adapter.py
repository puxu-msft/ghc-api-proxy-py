from __future__ import annotations

import asyncio
import json
import socket
from enum import StrEnum
from typing import Any, Protocol, cast

from uvicorn._types import ASGI3Application, ASGIReceiveCallable, ASGISendCallable, Scope
from uvicorn.config import Config
from uvicorn.server import Server, ServerState

from app.lifecycle.activation import ActivatedSocketSet, ListenerIdentity, SocketActivationError

# What a request gets when it arrives after admission has been refused. The Anthropic error envelope because that is what almost everything reaching this proxy is speaking, and a client that renders `error.message` then shows its user the actual reason rather than a parse failure. `overloaded_error` is Anthropic's own type for "ask again shortly", which is exactly the advice.
REFUSAL_STATUS = 503
REFUSAL_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"content-type", b"application/json"),
    # The connection is going away regardless; saying so keeps a pooled client from queueing more onto a socket we are about to close under it.
    (b"connection", b"close"),
)
# One byte is enough: the question is whether anything is waiting, not what it says. `MSG_DONTWAIT` is belt-and-braces — an asyncio transport's socket is already non-blocking — and is absent on platforms this service does not target, so it degrades to a plain peek rather than failing to import.
_PEEK_UNREAD = socket.MSG_PEEK | getattr(socket, "MSG_DONTWAIT", 0)

# 1012 is "service restart", and the rolling control plane already speaks it for the same event.
REFUSAL_WEBSOCKET_CODE = 1012


class ListenerAdapterError(RuntimeError):
    """Raised when the rolling listener adapter cannot change accept state."""


class ListenerState(StrEnum):
    NEW = "new"
    DORMANT = "dormant"
    ACCEPTING = "accepting"
    STOPPED = "stopped"
    STOPPING = "stopping"
    FAILED = "failed"
    CLOSED = "closed"


class _UvicornProtocolFactory(Protocol):
    def __call__(
        self,
        *,
        config: Config,
        server_state: ServerState,
        app_state: dict[str, Any],
        _loop: asyncio.AbstractEventLoop | None,
    ) -> asyncio.Protocol: ...


class _LoadedAppConfig(Protocol):
    loaded_app: object


class UvicornListenerAdapter:
    """Own Uvicorn protocol listeners without invoking Uvicorn's shutdown lifecycle."""

    def __init__(self, config: Config, activated: ActivatedSocketSet) -> None:
        self._config = config
        self._activated = activated
        self._server = Server(config)
        self._registrations: list[asyncio.Server] = []
        self._accept_duplicates: dict[str, socket.socket] = {}
        self._lifespan_started = False
        self._state = ListenerState.NEW
        self._operation_lock = asyncio.Lock()
        self._tick_task: asyncio.Task[None] | None = None
        self._tick_stop = asyncio.Event()
        self._admission_open = asyncio.Event()
        self._admission_refusal: str | None = None
        self._refused_requests = 0
        self._severed_connections = 0

    @property
    def server_state(self) -> ServerState:
        return self._server.server_state

    @property
    def accepting(self) -> bool:
        return self._state is ListenerState.ACCEPTING

    @property
    def state(self) -> ListenerState:
        return self._state

    @property
    def listener_identities(self) -> tuple[ListenerIdentity, ...]:
        return self._activated.identities()

    def registration_identities(self) -> tuple[tuple[int, int], ...]:
        identities: list[tuple[int, int]] = []
        for registration in self._registrations:
            for registered_socket in registration.sockets or ():
                stat = registered_socket.fileno()
                socket_stat = __import__("os").fstat(stat)
                identities.append((socket_stat.st_dev, socket_stat.st_ino))
        return tuple(sorted(identities))

    @property
    def registrations(self) -> tuple[asyncio.Server, ...]:
        return tuple(self._registrations)

    async def startup_lifespan(self) -> None:
        async with self._operation_lock:
            if self._lifespan_started:
                return
            if self._state is ListenerState.CLOSED:
                raise ListenerAdapterError("adapter is closed")
            if not self._config.loaded:
                self._config.load()
            self._install_admission_barrier()
            self._server.lifespan = self._config.lifespan_class(self._config)
            await self._server.lifespan.startup()
            if self._server.lifespan.should_exit:
                self._state = ListenerState.FAILED
                raise ListenerAdapterError("ASGI lifespan requested exit during startup")
            self._lifespan_started = True
            await self._server.on_tick(0)
            self._tick_stop.clear()
            self._tick_task = asyncio.create_task(self._run_ticks())

    async def register_dormant(self) -> None:
        async with self._operation_lock:
            await self._register_dormant_locked()

    async def arm(self) -> None:
        async with self._operation_lock:
            await self._arm_locked()

    async def stop_accepting(self) -> None:
        async with self._operation_lock:
            if self._state in {ListenerState.STOPPING, ListenerState.CLOSED}:
                return
            if self._state is ListenerState.FAILED:
                return
            self._close_registrations_locked(ListenerState.STOPPED)

    async def resume_accepting(self) -> None:
        async with self._operation_lock:
            if self._state is ListenerState.ACCEPTING:
                return
            if self._state is not ListenerState.STOPPED:
                raise ListenerAdapterError(
                    f"resume requires stopped state, got {self._state}"
                )
            if not self._registrations:
                await self._register_dormant_locked()
            await self._arm_locked()

    async def wait_drained(self, timeout: float | None = None) -> None:
        async def wait() -> None:
            while self._server.server_state.tasks:
                await asyncio.sleep(0.01)

        if timeout is None:
            await wait()
        else:
            await asyncio.wait_for(wait(), timeout)

    def connection_count(self) -> int:
        """How many client connections are currently open.

        Distinct from the number of requests in flight, and the difference is the point: a pooled client holds its connection between requests, so a count that stays at one with nothing running is the normal idle state — and a drain that will not finish is a count that will not fall.
        """
        return len(self._server.server_state.connections)

    def refused_requests(self) -> int:
        """How many requests the barrier answered with a 503 rather than passing on, since this adapter was built.

        Cumulative, so a caller wanting one shutdown's worth reads it before and after and subtracts.

        **Expect zero on the stand-alone shutdown path, and do not read that as "nobody went without".** Measured over eleven real-signal runs: `stop_admitting` closes the pooled connections in the same breath as it raises the refusal, so a client's next request finds no socket at all — an RST if its bytes were already on the wire, a bare EOF if not. Neither reaches this counter, and the RST case is the one that actually costs somebody, because an interrupted `POST` is not safely retryable. A non-zero value here means a request was genuinely parked at the barrier when the refusal landed: a `both`-mode quiesce window, or a caller driving the adapter directly.

        So this measures the mild outcome and cannot see the harsh one. It is worth reporting for what it is; it is not the number that tells you whether a restart hurt anyone, and an earlier version of this docstring claimed it was.
        """
        return self._refused_requests

    def severed_connections(self) -> int:
        """How many connections were closed at the drain with a request already sitting unread, since this adapter was built.

        Cumulative, like `refused_requests`, so one shutdown's worth is a before-and-after difference.

        This is the count that says a client genuinely went without, and it is the one `refused_requests` cannot see: a refused request got a 503 telling it to come back, while these got an RST and never reached the application at all. The two are deliberately separate because they are opposite ends of the same moment — the 503 is the drain working, this is the drain costing somebody.

        Under-counts rather than over-counts by construction; see `_closing_would_sever` for which cases it cannot see.
        """
        return self._severed_connections

    def interrupt_connections(self) -> int:
        """Ask every open connection to shut down, and report how many were asked.

        This is the escalation between waiting for requests and abandoning them.
        The connection stops reading and closes once its current response ends.
        A request is therefore cut short rather than killed mid-write.
        The count lets a caller say whether anything was actually interrupted.
        """
        connections = list(self._server.server_state.connections)
        for connection in connections:
            connection.shutdown()
        return len(connections)

    def cancel_requests(self) -> int:
        """Cancel the request tasks still running, and report how many were cancelled.

        `interrupt_connections` alone does not reach a handler that is mid-request: Uvicorn only
        clears `keep_alive` there and lets the response finish.
        Actually interrupting a request therefore means cancelling the task running it.
        Idempotent, so a caller may call it again without counting the same work twice.
        """
        tasks = [task for task in self._server.server_state.tasks if not task.done()]
        for task in tasks:
            task.cancel()
        return len(tasks)

    async def stop_admitting(self) -> int:
        """Stop taking new requests and let the pooled connections go, reporting how many were asked.

        The two halves are not equally load-bearing, and saying so matters to whoever weighs them next.

        **Refusing admission is the half that fixes the deadlock.** `stop_accepting` only closes the listener. A client that already holds a connection can still send on it, and the admission barrier — which exists so a rolling quiesce can hold a request until the listener resumes — would hold that request for a resume that a shutdown is never going to perform. The drain waits on the request tasks, so one held request is enough for the drain to never end. Refusing answers those requests instead of holding them.

        **Closing the connections is the half that tells the client sooner.** Measured by removing it: the drain still ends, because `shutdown_lifespan` closes the connections anyway a moment later. What this buys is that a pooled client learns during a long drain rather than at the end of it, so it stops sending into a process that has already promised to stop. Worth keeping, not load-bearing.

        Either way this is not the interruption rung. An idle pooled connection goes now; one with a request still running keeps it, because Uvicorn only clears `keep_alive` there and closes when that response ends. A response already being written is delivered in full.

        The count is of connections *asked*, the same reading `interrupt_connections` reports, and deliberately not of connections that went this instant. Only Uvicorn's own cycle state distinguishes the two, and a number derived from it would go quietly wrong the next time that internal changes, where a number that says what it counted stays true.

        Closing an idle connection is not free for every client, though, and `severed_connections` is where that shows up: each one is peeked at first, so a connection carrying bytes nobody has read yet is counted separately from one that was genuinely idle.

        Takes the lock although `interrupt_connections` does not, for the refusal rather than the connections: the refusal is one half of a two-field barrier state that the arm and register paths also write, and those hold this lock.
        """
        async with self._operation_lock:
            self._refuse_admission_locked("server is shutting down")
            connections = list(self._server.server_state.connections)
            for connection in connections:
                # Before the close, because afterwards there is nothing left to ask.
                if _closing_would_sever(connection):
                    self._severed_connections += 1
                connection.shutdown()
            return len(connections)

    async def shutdown_lifespan(self, *, drain_timeout: float | None = None) -> None:
        async with self._operation_lock:
            if self._state is ListenerState.CLOSED:
                return
            self._state = ListenerState.STOPPING
            self._refuse_admission_locked("server is shutting down")
            self._close_registrations_locked(ListenerState.STOPPING)
            for connection in list(self._server.server_state.connections):
                connection.shutdown()
        await self.wait_drained(drain_timeout)
        async with self._operation_lock:
            if not self._lifespan_started:
                return
            await self._stop_ticks_locked()
            await self._server.lifespan.shutdown()
            self._lifespan_started = False
            if self._server.lifespan.should_exit:
                self._state = ListenerState.FAILED
                raise ListenerAdapterError("ASGI lifespan failed during shutdown")
            self._state = ListenerState.CLOSED

    async def close_masters(self) -> None:
        async with self._operation_lock:
            if self._registrations:
                raise SocketActivationError("stop accepting before closing listener masters")
            self._activated.close()

    def open_admission(self) -> None:
        """Let arriving requests through, and forget any refusal that was in force.

        Public because the first-byte router in front of this adapter owns the accepts while this one owns the barrier, so it has to drive the barrier from outside. Handing it a method beats letting it reach in: reaching in reached one of the two fields, and a refusal left set behind an open gate answers 503 to every request on a listener that has just resumed.
        """
        self._admission_refusal = None
        self._admission_open.set()

    def pause_admission(self) -> None:
        """Hold arriving requests until admission opens again, which is what a rolling quiesce wants.

        The opposite of `stop_admitting`, and the distinction is the whole bug this pairing exists to keep straight: a pause is a promise that something will resume, and a shutdown makes no such promise.
        """
        self._admission_refusal = None
        self._admission_open.clear()

    def _protocol_factory(self):  # type: ignore[no-untyped-def]
        config = self._config
        server_state = self._server.server_state
        app_state: dict[str, Any] = self._server.lifespan.state
        protocol_factory = cast(_UvicornProtocolFactory, config.http_protocol_class)

        def create_protocol(
            loop: asyncio.AbstractEventLoop | None = None,
        ) -> asyncio.Protocol:
            return protocol_factory(
                config=config,
                server_state=server_state,
                app_state=app_state,
                _loop=loop,
            )

        return create_protocol

    async def _register_dormant_locked(self) -> None:
        if not self._lifespan_started:
            raise ListenerAdapterError("lifespan must start before listener registration")
        if self._state not in {ListenerState.NEW, ListenerState.STOPPED}:
            raise ListenerAdapterError(
                f"register requires new or stopped state, got {self._state}"
            )
        if self._registrations:
            raise ListenerAdapterError("listeners are already registered")
        duplicates = self._activated.duplicate_for_accept()
        registrations: list[asyncio.Server] = []
        loop = asyncio.get_running_loop()
        create_protocol = self._protocol_factory()
        try:
            for name in sorted(duplicates):
                registrations.append(
                    await loop.create_server(
                        create_protocol,
                        sock=duplicates[name],
                        ssl=self._config.ssl,
                        backlog=self._config.backlog,
                        start_serving=False,
                    )
                )
        except BaseException:
            for registration in registrations:
                registration.close()
            for duplicate in duplicates.values():
                duplicate.close()
            self._state = ListenerState.FAILED
            raise
        self._accept_duplicates = duplicates
        self._registrations = registrations
        self.pause_admission()
        self._state = ListenerState.DORMANT

    async def _arm_locked(self) -> None:
        if not self._registrations:
            raise ListenerAdapterError("listeners must be registered before arm")
        if self._state is ListenerState.ACCEPTING:
            return
        if self._state is not ListenerState.DORMANT:
            raise ListenerAdapterError(f"arm requires dormant state, got {self._state}")
        try:
            for registration in self._registrations:
                await registration.start_serving()
        except BaseException:
            self._refuse_admission_locked("listener failed to start accepting")
            self._close_registrations_locked(ListenerState.FAILED)
            raise
        self.open_admission()
        self._state = ListenerState.ACCEPTING

    def _close_registrations_locked(self, next_state: ListenerState) -> None:
        registrations, self._registrations = self._registrations, []
        duplicates, self._accept_duplicates = self._accept_duplicates, {}
        if next_state is ListenerState.STOPPED:
            self.pause_admission()
        for registration in registrations:
            registration.close()
        for duplicate in duplicates.values():
            duplicate.close()
        if self._state is not ListenerState.CLOSED:
            self._state = next_state

    async def _run_ticks(self) -> None:
        counter = 0
        while not self._tick_stop.is_set():
            await asyncio.sleep(0.1)
            counter = (counter + 1) % 864000
            await self._server.on_tick(counter)

    async def _stop_ticks_locked(self) -> None:
        self._tick_stop.set()
        task, self._tick_task = self._tick_task, None
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    def _install_admission_barrier(self) -> None:
        loaded_config = cast(_LoadedAppConfig, self._config)
        raw_loaded_app = loaded_config.loaded_app
        loaded_app = cast(ASGI3Application, raw_loaded_app)

        async def gated_app(
            scope: Scope,
            receive: ASGIReceiveCallable,
            send: ASGISendCallable,
        ) -> None:
            if scope["type"] in {"http", "websocket"}:
                # Read off `self`, not captured, so that both halves of the barrier state are read the same way. Capturing the event by value made "this object is never rebound" an invariant nothing declared and nothing tested — and rebinding it is the natural way to write a reset, whose symptom would be a silent permanent hang, the very shape this barrier's last bug had.
                await self._admission_open.wait()
                refusal = self._admission_refusal
                if refusal is not None:
                    # Answered rather than raised. Raising here reached Uvicorn as an unhandled application error: the client got a bare 500 with no reason in it, and the log got an "Exception in ASGI application" traceback for what is a planned, ordinary event.
                    self._refused_requests += 1
                    await _refuse_admission(scope, receive, send, refusal)
                    return
            await loaded_app(scope, receive, send)

        self._config.loaded_app = gated_app

    def _refuse_admission_locked(self, reason: str) -> None:
        """Turn the barrier from "wait for the listener" into "this request is not being served".

        The event is set either way, because a request waiting on it is waiting for an answer that only arrives when something opens the gate. Leaving it clear is what made a refused request wait forever.
        """
        self._admission_refusal = reason
        self._admission_open.set()


def _closing_would_sever(connection: object) -> bool:
    """Whether closing this connection now would throw away bytes the client already sent.

    This is the difference between the two costs a drain can impose. Closing a genuinely idle pooled connection costs the client nothing: it notices the EOF and opens a new one elsewhere. Closing one whose kernel receive buffer already holds an unread request destroys that request, and because the unread bytes make the kernel answer with an RST rather than a FIN, the client sees a connection reset rather than a refusal — for a non-idempotent `POST` that is not safely retryable, and it is invisible everywhere else in this process because those bytes never reached the application.

    `MSG_PEEK` leaves the data in place, so the event loop still delivers it to whoever would have read it; this only asks whether it is there.

    Two limits, both erring towards under-counting, which is the safe direction for a number that appears next to the word "severed":

    - a connection with a response still in progress is not being closed at all here, so it is not counted, even if its client has pipelined further bytes;
    - under TLS the bytes may already have been drained into the SSL object rather than left in the kernel buffer, and a peek then reports nothing.
    """
    cycle = getattr(connection, "cycle", None)
    if cycle is not None and not getattr(cycle, "response_complete", False):
        # Uvicorn only clears `keep_alive` for this one; the response finishes and nothing is lost.
        return False
    transport = getattr(connection, "transport", None)
    raw_socket = transport.get_extra_info("socket") if transport is not None else None
    if raw_socket is None:
        return False
    try:
        # `get_extra_info` hands back asyncio's `TransportSocket`, which refuses I/O on purpose so that nobody reads bytes out from under the event loop. Peeking is exactly the exception — it consumes nothing — so the descriptor is borrowed rather than the wrapper used, and `detach` gives it back without closing it.
        probe = socket.socket(fileno=raw_socket.fileno())
    except OSError:
        return False
    try:
        return bool(probe.recv(1, _PEEK_UNREAD))
    except (BlockingIOError, InterruptedError):
        # Nothing waiting, which is the ordinary idle case.
        return False
    except OSError:
        # Already unusable, so closing it takes nothing from anybody. Reported as not-severed rather than raised: a probe that cannot answer must not take down the shutdown it was measuring.
        return False
    finally:
        probe.detach()


async def _refuse_admission(
    scope: Scope,
    receive: ASGIReceiveCallable,
    send: ASGISendCallable,
    reason: str,
) -> None:
    """Tell one caller the server is not taking it, in whatever protocol it arrived on."""
    if scope["type"] == "websocket":
        # ASGI has the application take `websocket.connect` off the queue before it answers. Uvicorn does not police the order, but an intermediary that does would fault a close sent before the connect was read.
        await receive()
        # Refused before the handshake, so this is a rejection rather than a close: Uvicorn discards the code and the reason and answers HTTP 403. The code is what this would mean if it were ever sent after an accept, and is kept as the intent; nothing downstream sees the number today.
        await send({"type": "websocket.close", "code": REFUSAL_WEBSOCKET_CODE, "reason": reason})
        return
    body = json.dumps(
        {"type": "error", "error": {"type": "overloaded_error", "message": reason}}
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": REFUSAL_STATUS,
            "headers": [
                *REFUSAL_HEADERS,
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})
