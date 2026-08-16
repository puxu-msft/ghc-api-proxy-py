"""The direct-run entry: bind, serve, and hand over to a replacement.

`lifecycle.md` describes a smooth restart as two processes overlapping, not one process re-binding.
The replacement starts with `--restart` and takes the same port under `SO_REUSEPORT`.
It then sends the outgoing process SIGUSR2, which begins its drain without cutting anything short.

Finding the outgoing process is the pidfile's job.
It refuses to name a process it cannot verify, so an unrelated process never receives the signal.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from uvicorn import Config
from uvicorn._types import ASGIApplication

from app.config.paths import standalone_pidfile_path
from app.lifecycle.listener import adopt_listener, bind_listener
from app.lifecycle.pidfile import live_predecessor, remove_pidfile, signal_restart, write_pidfile
from app.lifecycle.standalone import ShutdownReport, StandaloneServer
from app.server_adapter import UvicornListenerAdapter

# Mirrors what `uvicorn.Config` accepts, so a FastAPI instance passes without a cast.
type Application = ASGIApplication | Callable[..., Any]


@dataclass(frozen=True, slots=True)
class StandaloneOptions:
    host: str = "127.0.0.1"
    port: int = 4142
    # An inherited listener; when set, nothing is bound and host/port are read off the socket.
    fd: int | None = None
    cleanup_timeout: int = 0
    pidfile: Path | None = None
    restart: bool = False

    def pidfile_path(self) -> Path:
        return self.pidfile if self.pidfile is not None else standalone_pidfile_path()


@dataclass(frozen=True, slots=True)
class StandaloneOutcome:
    report: ShutdownReport
    address: tuple[str, int]
    signalled_predecessor: int | None = None


async def run_standalone(
    application: Application,
    options: StandaloneOptions,
) -> StandaloneOutcome:
    """Serve until the shutdown ladder finishes, then release everything.

    The predecessor is signalled only once this process is listening.
    Signalling first would ask it to stop while nothing else could accept yet, opening the very gap
    the restart exists to avoid.
    """
    pidfile = options.pidfile_path()
    predecessor = live_predecessor(pidfile) if options.restart else None

    listeners = (
        adopt_listener(options.fd)
        if options.fd is not None
        else bind_listener(options.host, options.port)
    )
    address = listeners.identities()[0].address

    adapter = UvicornListenerAdapter(Config(application, log_config=None), listeners)

    async def announce() -> None:
        # Recorded only once accepting, so the file never names a process that cannot serve.
        write_pidfile(pidfile)
        if predecessor is not None:
            signal_restart(predecessor)

    server = StandaloneServer(
        adapter,
        cleanup_timeout=options.cleanup_timeout,
        on_serving=announce,
    )

    try:
        report = await server.serve()
    finally:
        remove_pidfile(pidfile)
    return StandaloneOutcome(
        report=report,
        address=address,
        signalled_predecessor=predecessor,
    )
