"""The in-flight request registry that feeds the live footer.

One process-wide registry, written from the request path and read by the footer renderer. Those are **two different threads**: requests are served on the event loop, while `rich.Live` refreshes from a thread of its own. So every access takes a lock.

An earlier version of this file claimed a lock was unnecessary because "every mutation happens on the event loop thread". That was true of the mutations and false of the reads, and the gap is not theoretical — building the snapshot iterates the mapping, and a review reproduced `RuntimeError: dictionary keys changed during iteration` under concurrent load. The refresh thread dies with it and the footer freezes at whatever it last drew.

The tracking boundary is deliberately not the handler's return. A streaming request has produced no bytes at the moment its handler returns — the body is consumed afterwards — so deregistering there would drop each streaming request off the footer at exactly the moment it starts being worth watching. `track_stream` exists to hold the registration open across the generator instead.
"""

import threading
import time
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field

from app.observability.footer import ActiveRequest


@dataclass(slots=True)
class _Entry:
    model: str
    started_at: float
    bytes_out: int | None = None
    attempts: int = 1


@dataclass(slots=True)
class ActiveRequestRegistry:
    _entries: dict[str, _Entry] = field(default_factory=lambda: dict[str, _Entry]())
    # Uncontended in practice — the critical sections are a dict write or a short copy — so the cost is a few tens of nanoseconds on a path that is already doing network I/O.
    _lock: threading.Lock = field(default_factory=threading.Lock)
    # Set once the listener stops accepting. Held here rather than passed to each render because the renderer runs on its own thread and needs somewhere to read it from that is not a moving argument.
    _draining: bool = False
    # Read on demand rather than stored, because the count changes without this class being told and a copy would be stale before it was drawn. `None` until the listener exists, and on the inherited-descriptor path where nobody owns a count to publish.
    connection_count: Callable[[], int] | None = None

    def connections(self) -> int:
        """Open client connections, or zero when nothing is publishing a count."""
        source = self.connection_count
        return source() if source is not None else 0

    @property
    def draining(self) -> bool:
        """Whether new requests are no longer being accepted while old ones finish.

        A distinct state from both running and stopped, and the one an operator most needs named: the process is still busy, but nothing further will arrive, so the list on screen can only shrink.
        """
        with self._lock:
            return self._draining

    def begin_draining(self) -> None:
        with self._lock:
            self._draining = True

    def snapshot(self) -> list[ActiveRequest]:
        """A detached view for the renderer, so a mutation mid-render cannot change what it is drawing.

        Built inside the lock: the detachment is what protects the *caller*, and the iteration that produces it is exactly what needs protecting from a concurrent write.
        """
        with self._lock:
            return [
                ActiveRequest(
                    request_id=request_id,
                    model=entry.model,
                    started_at=entry.started_at,
                    bytes_out=entry.bytes_out,
                    attempts=entry.attempts,
                )
                for request_id, entry in self._entries.items()
            ]

    def add(self, request_id: str, *, model: str = "", started_at: float | None = None) -> None:
        with self._lock:
            self._entries[request_id] = _Entry(model=model, started_at=started_at if started_at is not None else time.monotonic())

    def remove(self, request_id: str) -> None:
        with self._lock:
            self._entries.pop(request_id, None)

    def set_model(self, request_id: str, model: str) -> None:
        """Routing resolves the model after the request is already registered, so the footer shows `(resolving)` first and the real name once it is known."""
        with self._lock:
            entry = self._entries.get(request_id)
            if entry is not None:
                entry.model = model

    def set_attempts(self, request_id: str, attempts: int) -> None:
        with self._lock:
            entry = self._entries.get(request_id)
            if entry is not None:
                entry.attempts = attempts

    def add_bytes(self, request_id: str, count: int) -> None:
        """Record downstream progress. The first call is what turns `↓` on: until then the footer shows no byte field at all, which reads as "nothing has streamed back yet" rather than "zero bytes"."""
        with self._lock:
            entry = self._entries.get(request_id)
            if entry is not None:
                entry.bytes_out = (entry.bytes_out or 0) + count

    @contextmanager
    def track(self, request_id: str, *, model: str = "") -> Generator[None]:
        """Hold a registration for the duration of a non-streaming request."""
        self.add(request_id, model=model)
        try:
            yield
        finally:
            self.remove(request_id)

    @asynccontextmanager
    async def track_stream(self, request_id: str, *, model: str = "") -> AsyncGenerator[None]:
        """Hold a registration across a streaming body, which outlives the handler that produced it."""
        self.add(request_id, model=model)
        try:
            yield
        finally:
            self.remove(request_id)
