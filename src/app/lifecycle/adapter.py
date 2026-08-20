from __future__ import annotations

import asyncio
import socket
from enum import StrEnum
from typing import Any, Protocol, cast

from uvicorn._types import ASGI3Application, ASGIReceiveCallable, ASGISendCallable, Scope
from uvicorn.config import Config
from uvicorn.server import Server, ServerState

from app.lifecycle.activation import ActivatedSocketSet, ListenerIdentity, SocketActivationError


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
        self._admission_error: ListenerAdapterError | None = None

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

    async def shutdown_lifespan(self, *, drain_timeout: float | None = None) -> None:
        async with self._operation_lock:
            if self._state is ListenerState.CLOSED:
                return
            self._state = ListenerState.STOPPING
            self._reject_pending_admission_locked("adapter is stopping")
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
        self._admission_error = None
        self._admission_open.clear()
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
            self._reject_pending_admission_locked("listener arm failed")
            self._close_registrations_locked(ListenerState.FAILED)
            raise
        self._admission_error = None
        self._admission_open.set()
        self._state = ListenerState.ACCEPTING

    def _close_registrations_locked(self, next_state: ListenerState) -> None:
        registrations, self._registrations = self._registrations, []
        duplicates, self._accept_duplicates = self._accept_duplicates, {}
        if next_state is ListenerState.STOPPED:
            self._admission_error = None
            self._admission_open.clear()
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
        admission_open = self._admission_open

        async def gated_app(
            scope: Scope,
            receive: ASGIReceiveCallable,
            send: ASGISendCallable,
        ) -> None:
            if scope["type"] in {"http", "websocket"}:
                await admission_open.wait()
                if self._admission_error is not None:
                    raise self._admission_error
            await loaded_app(scope, receive, send)

        self._config.loaded_app = gated_app

    def _reject_pending_admission_locked(self, message: str) -> None:
        self._admission_error = ListenerAdapterError(message)
        self._admission_open.set()
