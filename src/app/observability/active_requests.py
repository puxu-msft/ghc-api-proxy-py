"""The in-flight request registry that feeds the live footer.

One process-wide registry, mutated from the request path and read by the footer renderer. No lock: every mutation happens on the event loop thread, and the renderer reads a snapshot rather than holding the live mapping.

The tracking boundary is deliberately not the handler's return. A streaming request has produced no bytes at the moment its handler returns — the body is consumed afterwards — so deregistering there would drop each streaming request off the footer at exactly the moment it starts being worth watching. `track_stream` exists to hold the registration open across the generator instead.
"""

import time
from collections.abc import AsyncGenerator, Generator
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

    def snapshot(self) -> list[ActiveRequest]:
        """A detached view for the renderer, so a mutation mid-render cannot change what it is drawing."""
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
        self._entries[request_id] = _Entry(model=model, started_at=started_at if started_at is not None else time.monotonic())

    def remove(self, request_id: str) -> None:
        self._entries.pop(request_id, None)

    def set_model(self, request_id: str, model: str) -> None:
        """Routing resolves the model after the request is already registered, so the footer shows `(resolving)` first and the real name once it is known."""
        entry = self._entries.get(request_id)
        if entry is not None:
            entry.model = model

    def set_attempts(self, request_id: str, attempts: int) -> None:
        entry = self._entries.get(request_id)
        if entry is not None:
            entry.attempts = attempts

    def add_bytes(self, request_id: str, count: int) -> None:
        """Record downstream progress. The first call is what turns `↓` on: until then the footer shows no byte field at all, which reads as "nothing has streamed back yet" rather than "zero bytes"."""
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
