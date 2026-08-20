"""Binding the listener a directly-run process owns.

Under systemd the listener comes from socket activation and the process never binds.
Run directly there is nobody to inherit from, so the process binds its own.
It binds the way the spec's smooth restart needs, with `SO_REUSEPORT`.

That option is what lets the replacement bind the same port while the old process still listens.
Without it the second bind fails with EADDRINUSE.
The restart then has to become a stop-then-start, with a window where the port answers nothing.

The result is wrapped in `ActivatedSocketSet`.
A self-bound listener and an inherited one are then the same kind of thing from here on.
Both reach `UvicornListenerAdapter` unchanged.
"""

import asyncio
import logging
import socket
import ssl
from collections.abc import Callable

from app.lifecycle.activation import ActivatedSocketSet, ExpectedListener, ListenerIdentity
from app.lifecycle.adapter import ListenerAdapterError, ListenerState, UvicornListenerAdapter
from app.server.tls import is_tls_handshake

LISTENER_NAME = "http"
LOGGER = logging.getLogger(__name__)


class ListenerBindError(RuntimeError):
    """The configured address could not be turned into a listening socket."""


def _resolve(host: str, port: int) -> tuple[socket.AddressFamily, tuple[str, int]]:
    """Pick one address to bind, preferring IPv4 so `getsockname` matches what was configured."""
    try:
        candidates = socket.getaddrinfo(
            host or None,
            port,
            type=socket.SOCK_STREAM,
            flags=socket.AI_PASSIVE,
        )
    except OSError as error:
        raise ListenerBindError(f"cannot resolve {host!r}:{port}: {error}") from error
    for family, _type, _proto, _canon, address in candidates:
        if family is socket.AF_INET:
            return family, (str(address[0]), int(address[1]))
    for family, _type, _proto, _canon, address in candidates:
        if family is socket.AF_INET6:
            return family, (str(address[0]), int(address[1]))
    raise ListenerBindError(f"no IPv4 or IPv6 address for {host!r}:{port}")


def adopt_listener(fd: int) -> ActivatedSocketSet:
    """Wrap a listening socket this process was handed, without binding anything.

    The address is read back off the socket rather than taken from configuration, so an inherited
    listener cannot be described as something it is not.
    """
    try:
        sock = socket.socket(fileno=fd)
    except OSError as error:
        raise ListenerBindError(f"cannot adopt fd {fd}: {error}") from error
    try:
        bound = sock.getsockname()
        expected = ExpectedListener(
            name=LISTENER_NAME,
            family=sock.family,
            host=str(bound[0]),
            port=int(bound[1]),
        )
        return ActivatedSocketSet({LISTENER_NAME: sock}, [expected])
    except OSError as error:
        raise ListenerBindError(f"cannot adopt fd {fd}: {error}") from error
    finally:
        sock.close()


def bind_listener(host: str, port: int, *, reuse_port: bool = True) -> ActivatedSocketSet:
    """Bind and listen, returning the same listener container the systemd path produces.

    `reuse_port` defaults on.
    A process that binds without it cannot be smoothly replaced, and by then it is too late to say.
    """
    family, address = _resolve(host, port)
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        # Lets a restart rebind while the old socket is in TIME_WAIT.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if reuse_port:
            if not hasattr(socket, "SO_REUSEPORT"):
                raise ListenerBindError("SO_REUSEPORT is unavailable on this platform")
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(address)
        sock.listen()
        sock.set_inheritable(True)
        # Read the address back: port 0 means the kernel chose, and the caller must be told which.
        bound = sock.getsockname()
        expected = ExpectedListener(
            name=LISTENER_NAME,
            family=family,
            host=str(bound[0]),
            port=int(bound[1]),
        )
        return ActivatedSocketSet({LISTENER_NAME: sock}, [expected])
    except OSError as error:
        raise ListenerBindError(f"cannot bind {address!r}: {error}") from error
    finally:
        # ActivatedSocketSet keeps its own duplicate, so this one is ours to close either way.
        sock.close()


class FirstByteRoutingAdapter:
    """Route accepted connections to plaintext or TLS Uvicorn protocols without consuming a byte.

    This adapter owns only accepts. The wrapped adapter owns Uvicorn lifecycle and connection state.
    Closing duplicate accept sockets leaves the ActivatedSocketSet masters open.
    Stop/resume therefore keeps listener identity intact.
    """

    def __init__(
        self,
        adapter: UvicornListenerAdapter,
        listeners: ActivatedSocketSet,
        tls_context: ssl.SSLContext,
    ) -> None:
        self._adapter = adapter
        self._listeners = listeners
        self._tls_context = tls_context
        self._accept_sockets: dict[str, socket.socket] = {}
        self._pending_sockets: set[socket.socket] = set()
        self._routing_tasks: set[asyncio.Task[None]] = set()
        self._operation_lock = asyncio.Lock()
        self._protocol_factory: Callable[[], asyncio.Protocol] | None = None
        self._lifespan_started = False
        self._state = ListenerState.NEW

    @property
    def server_state(self):  # type: ignore[no-untyped-def]
        return self._adapter.server_state

    @property
    def accepting(self) -> bool:
        return self._state is ListenerState.ACCEPTING

    @property
    def state(self) -> ListenerState:
        return self._state

    @property
    def listener_identities(self) -> tuple[ListenerIdentity, ...]:
        return self._listeners.identities()

    def registration_identities(self) -> tuple[tuple[int, int], ...]:
        identities: list[tuple[int, int]] = []
        for accept_socket in self._accept_sockets.values():
            stat = __import__("os").fstat(accept_socket.fileno())
            identities.append((stat.st_dev, stat.st_ino))
        return tuple(sorted(identities))

    async def startup_lifespan(self) -> None:
        async with self._operation_lock:
            if self._lifespan_started:
                return
            await self._adapter.startup_lifespan()
            # Uvicorn's protocol factory is created only after Config.load() in startup_lifespan.
            factory = self._adapter._protocol_factory  # pyright: ignore[reportPrivateUsage]
            self._protocol_factory = factory()
            self._lifespan_started = True

    async def register_dormant(self) -> None:
        async with self._operation_lock:
            self._register_dormant_locked()

    def _register_dormant_locked(self) -> None:
        if not self._lifespan_started:
            raise ListenerAdapterError("lifespan must start before listener registration")
        if self._state not in {ListenerState.NEW, ListenerState.STOPPED}:
            raise ListenerAdapterError(f"register requires new or stopped state, got {self._state}")
        if self._accept_sockets:
            raise ListenerAdapterError("listeners are already registered")
        accept_sockets = self._listeners.duplicate_for_accept()
        try:
            for accept_socket in accept_sockets.values():
                accept_socket.setblocking(False)
        except BaseException:
            for accept_socket in accept_sockets.values():
                accept_socket.close()
            raise
        self._accept_sockets = accept_sockets
        self._state = ListenerState.DORMANT

    async def arm(self) -> None:
        async with self._operation_lock:
            self._arm_locked()

    def _arm_locked(self) -> None:
        if not self._accept_sockets:
            raise ListenerAdapterError("listeners must be registered before arm")
        if self._state is ListenerState.ACCEPTING:
            return
        if self._state is not ListenerState.DORMANT:
            raise ListenerAdapterError(f"arm requires dormant state, got {self._state}")
        loop = asyncio.get_running_loop()
        registered: list[socket.socket] = []
        try:
            for accept_socket in self._accept_sockets.values():
                loop.add_reader(accept_socket.fileno(), self._accept_ready, accept_socket)
                registered.append(accept_socket)
        except BaseException:
            for accept_socket in registered:
                loop.remove_reader(accept_socket.fileno())
            self._state = ListenerState.FAILED
            raise
        # The wrapped adapter owns the Uvicorn admission barrier, but this adapter owns accepts.
        self._adapter.open_admission()
        self._state = ListenerState.ACCEPTING

    async def stop_accepting(self) -> None:
        async with self._operation_lock:
            if self._state in {ListenerState.STOPPING, ListenerState.CLOSED, ListenerState.FAILED}:
                return
            accept_sockets, self._accept_sockets = self._accept_sockets, {}
            loop = asyncio.get_running_loop()
            for accept_socket in accept_sockets.values():
                loop.remove_reader(accept_socket.fileno())
                accept_socket.close()
            # Close pending clients before cancellation to release an idle first-byte wait.
            for pending_socket in self._pending_sockets:
                pending_socket.close()
            routing_tasks = tuple(self._routing_tasks)
            for task in routing_tasks:
                task.cancel()
            self._adapter.pause_admission()
            self._state = ListenerState.STOPPED
        if routing_tasks:
            # Cancellation is expected here; unexpected route failures are reported by the callback.
            await asyncio.gather(*routing_tasks, return_exceptions=True)

    async def resume_accepting(self) -> None:
        async with self._operation_lock:
            if self._state is ListenerState.ACCEPTING:
                return
            if self._state is not ListenerState.STOPPED:
                raise ListenerAdapterError(f"resume requires stopped state, got {self._state}")
            self._register_dormant_locked()
            self._arm_locked()

    async def wait_drained(self, timeout: float | None = None) -> None:
        await self._adapter.wait_drained(timeout)

    def interrupt_connections(self) -> int:
        return self._adapter.interrupt_connections()

    async def stop_admitting(self) -> int:
        # Every accepted socket ends up behind the wrapped adapter, and `stop_accepting` has already dealt with this router's own half — the sockets still waiting on a first byte.
        return await self._adapter.stop_admitting()

    def refused_requests(self) -> int:
        return self._adapter.refused_requests()

    def severed_connections(self) -> int:
        return self._adapter.severed_connections()

    def connection_count(self) -> int:
        # The router owns no connections of its own; every accepted socket is handed to the adapter behind it, so the count it keeps is the whole count.
        return self._adapter.connection_count()

    def cancel_requests(self) -> int:
        return self._adapter.cancel_requests()

    async def shutdown_lifespan(self, *, drain_timeout: float | None = None) -> None:
        await self.stop_accepting()
        await self._adapter.shutdown_lifespan(drain_timeout=drain_timeout)
        self._state = ListenerState.CLOSED

    async def close_masters(self) -> None:
        if self._accept_sockets:
            raise ListenerAdapterError("stop accepting before closing listener masters")
        await self._adapter.close_masters()

    def _accept_ready(self, accept_socket: socket.socket) -> None:
        loop = asyncio.get_running_loop()
        while True:
            try:
                client_socket, _address = accept_socket.accept()
            except BlockingIOError:
                return
            except OSError:
                # Report accept failure; listener readiness is no longer trustworthy.
                raise
            client_socket.setblocking(False)
            task = loop.create_task(self._route_connection(client_socket))
            self._routing_tasks.add(task)
            task.add_done_callback(self._finish_routing_task)

    async def _route_connection(self, client_socket: socket.socket) -> None:
        self._pending_sockets.add(client_socket)
        transferred = False
        try:
            first_byte = await self._peek_first_byte(client_socket)
            if not first_byte:
                return
            protocol_factory = self._protocol_factory
            if protocol_factory is None:
                raise ListenerAdapterError("TLS router started without a Uvicorn protocol factory")
            tls_context = self._tls_context if is_tls_handshake(first_byte[0]) else None
            loop = asyncio.get_running_loop()
            await loop.connect_accepted_socket(protocol_factory, client_socket, ssl=tls_context)
            transferred = True
        except asyncio.CancelledError:
            raise
        except OSError as error:
            # A bad TLS handshake belongs to this client only; retain the listener and report it.
            LOGGER.warning("failed to route accepted TLS connection", exc_info=error)
        finally:
            self._pending_sockets.discard(client_socket)
            if not transferred:
                client_socket.close()

    async def _peek_first_byte(self, client_socket: socket.socket) -> bytes:
        loop = asyncio.get_running_loop()
        first_byte: asyncio.Future[bytes] = loop.create_future()

        def read_first_byte() -> None:
            try:
                value = client_socket.recv(1, socket.MSG_PEEK)
            except BlockingIOError:
                return
            except OSError as error:
                if not first_byte.done():
                    first_byte.set_exception(error)
                return
            if not first_byte.done():
                first_byte.set_result(value)

        loop.add_reader(client_socket.fileno(), read_first_byte)
        try:
            return await first_byte
        finally:
            loop.remove_reader(client_socket.fileno())

    def _finish_routing_task(self, task: asyncio.Task[None]) -> None:
        self._routing_tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            LOGGER.error("accepted connection routing crashed", exc_info=error)
