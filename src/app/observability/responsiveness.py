"""Low-rate timing at the event-loop, footer and terminal-call boundaries.

Nothing here logs or inspects stacks. The terminal delegate belongs only to the footer's Console; Rich remains the owner of stdout/stderr redirection and its restoration.
"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, TextIO, cast

import anyio
from rich.file_proxy import FileProxy

from app.observability.metrics import RESPONSIVENESS, ResponsivenessMetrics

HEARTBEAT_SECONDS = 0.5


async def monitor_event_loop(metrics: ResponsivenessMetrics = RESPONSIVENESS) -> None:
    metrics.loop_active.inc()
    try:
        while True:
            due = metrics.clock() + HEARTBEAT_SECONDS
            await anyio.sleep(HEARTBEAT_SECONDS)
            metrics.loop_lag.observe(metrics.clock() - due)
    finally:
        metrics.loop_active.dec()


@contextmanager
def observe_tui(metrics: ResponsivenessMetrics, owner: object) -> Generator[None]:
    metrics.activate(owner)
    try:
        yield
    finally:
        metrics.deactivate(owner)


@contextmanager
def observe_render(metrics: ResponsivenessMetrics, owner: object) -> Generator[None]:
    started = metrics.clock()
    if not metrics.render_started(owner, started):
        # Pure-render callers outside a live lifecycle do not claim to refresh a terminal.
        yield
        return
    failed = True
    try:
        yield
        failed = False
    finally:
        ended = metrics.clock()
        if not failed:
            metrics.render_succeeded(owner, ended)
        metrics.render_duration.observe(ended - started, failed=failed)


class ObservedTerminal:
    """Delegate unchanged TextIO operations without owning or closing the stream."""

    def __init__(self, stream: TextIO, metrics: ResponsivenessMetrics, owner: object) -> None:
        # Console.file unwraps FileProxy before writing. Normalize it here too, or our attribute delegation exposes rich_proxied_file and Console silently bypasses the timing wrapper when another Live already owns stderr.
        while isinstance(stream, FileProxy):
            stream = cast(TextIO, stream.rich_proxied_file)
        self._stream = stream
        self._metrics = metrics
        self._owner = owner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)

    @contextmanager
    def _operation(self, operation: str) -> Generator[None]:
        metrics = self._metrics
        started = metrics.clock()
        token = object()
        metrics.io_started(self._owner, operation, token, started)
        failed = True
        try:
            yield
            failed = False
        finally:
            ended = metrics.clock()
            metrics.io_finished(operation, token)
            metrics.terminal_io[operation].observe(ended - started, failed=failed)

    def write(self, text: str) -> int:
        with self._operation("write"):
            return self._stream.write(text)

    def flush(self) -> None:
        with self._operation("flush"):
            return self._stream.flush()
