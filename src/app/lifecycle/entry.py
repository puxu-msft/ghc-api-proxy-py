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
from app.config.schema import TlsMode
from app.lifecycle.adapter import UvicornListenerAdapter
from app.lifecycle.listener import FirstByteRoutingAdapter, adopt_listener, bind_listener
from app.lifecycle.pidfile import (
    live_predecessor,
    remove_pidfile,
    signal_restart,
    write_entry,
    write_pidfile,
)
from app.lifecycle.standalone import ShutdownReport, StandaloneServer
from app.server.tls import TlsMaterial, build_server_ssl_context

# Mirrors what `uvicorn.Config` accepts, so a FastAPI instance passes without a cast.
type Application = ASGIApplication | Callable[..., Any]


@dataclass(frozen=True, slots=True)
class StandaloneOptions:
    host: str = "127.0.0.1"
    port: int = 4142
    # An inherited listener; when set, nothing is bound and host/port are read off the socket.
    fd: int | None = None
    tls_mode: TlsMode = False
    tls_material: TlsMaterial | None = None
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
    on_draining: Callable[[], None] | None = None,
    on_observable: Callable[[Callable[[], int]], None] | None = None,
) -> StandaloneOutcome:
    """Serve until the shutdown ladder finishes, then release everything.

    The predecessor is signalled only once this process is listening.
    Signalling first would ask it to stop while nothing else could accept yet, opening the very gap
    the restart exists to avoid.

    `on_draining` is a parameter rather than a field of `StandaloneOptions` because the options
    describe the listener; this is a hook for whoever is watching, and the two have no reason to
    travel together.

    `on_observable` is handed the live connection count once the adapter exists. A number rather
    than a snapshot, because a display reads it on its own schedule and a value copied out here
    would be stale before it was drawn.
    """
    pidfile = options.pidfile_path()
    predecessor = live_predecessor(pidfile) if options.restart else None

    listeners = (
        adopt_listener(options.fd)
        if options.fd is not None
        else bind_listener(options.host, options.port)
    )
    address = listeners.identities()[0].address

    adapter: UvicornListenerAdapter | FirstByteRoutingAdapter
    if options.tls_mode is True:
        material = options.tls_material
        if material is None:
            raise ValueError("TLS mode requires certificate material")
        config = Config(
            application,
            log_config=None,
            ssl_certfile=material.cert_path,
            ssl_keyfile=material.key_path,
        )
        adapter = UvicornListenerAdapter(config, listeners)
    else:
        adapter = UvicornListenerAdapter(Config(application, log_config=None), listeners)
        if options.tls_mode == "both":
            material = options.tls_material
            if material is None:
                raise ValueError("TLS mode requires certificate material")
            adapter = FirstByteRoutingAdapter(
                adapter,
                listeners,
                build_server_ssl_context(material),
            )
    announced = False

    if on_observable is not None:
        on_observable(adapter.connection_count)

    async def announce() -> None:
        nonlocal announced
        # Recorded only once accepting, so the file never names a process that cannot serve.
        write_pidfile(pidfile)
        announced = True
        if predecessor is not None:
            signal_restart(predecessor)

    server = StandaloneServer(
        adapter,
        cleanup_timeout=options.cleanup_timeout,
        on_serving=announce,
        on_draining=on_draining,
    )

    try:
        report = await server.serve()
    except BaseException:
        # A start that never became a running server must not leave the predecessor without the
        # pidfile it is still the rightful owner of; it is the live process, and we are not.
        # The original record goes back verbatim: re-deriving its token would read whoever holds
        # that PID now, which is the one case the token exists to catch.
        if announced and predecessor is not None:
            write_entry(pidfile, predecessor)
        elif announced:
            remove_pidfile(pidfile)
        raise
    else:
        remove_pidfile(pidfile)
    return StandaloneOutcome(
        report=report,
        address=address,
        signalled_predecessor=predecessor.pid if predecessor is not None else None,
    )
