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
    PidfileEntry,
    PidfileError,
    look_up_predecessor,
    read_pidfile,
    remove_pidfile,
    signal_restart,
    write_entry,
    write_pidfile,
)
from app.lifecycle.standalone import LIFECYCLE_LOGGER, ShutdownReport, StandaloneServer
from app.observability.logging import get_logger
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
    pidfile_dir: Path | None = None
    restart: bool = False
    # Overwrite a record that still names a live process. Off by default: doing that is what left a serving process unfindable in the first place.
    force_write_pidfile: bool = False

    def pidfile_path(self, port: int) -> Path:
        """Where this process records itself, given the port it actually ended up listening on.

        The port is a parameter rather than read off `self.port` because that field is a request and this one is the result. Today the two always agree: `--port` and `server.port` are both constrained to 1..65535, and `--fd` never reaches here at all — systemd's listener is driven by `serve_inherited`, which owns no pidfile. Naming the file after the address that was actually bound is nonetheless the only spelling that stays correct if either of those constraints is relaxed, and it costs nothing to read the number back from the socket instead of trusting what was asked for.
        """
        return standalone_pidfile_path(port, self.pidfile_dir)


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
    listeners = (
        adopt_listener(options.fd)
        if options.fd is not None
        else bind_listener(options.host, options.port)
    )
    address = listeners.identities()[0].address

    # Resolved after the bind, so the name comes from the endpoint that exists rather than the one that was requested. See `pidfile_path` for why that distinction is worth keeping even though the two agree on every route the CLI can take today.
    pidfile = options.pidfile_path(address[1])
    # Looked up unconditionally, because both questions are asked of the same record: `--restart` wants to know who to hand over from, and every other start wants to know whether it is about to erase somebody.
    lookup = look_up_predecessor(pidfile)
    predecessor: PidfileEntry | None = lookup.entry if options.restart else None

    if options.restart:
        if predecessor is None:
            # `--restart` is an intention, and until now its failure was indistinguishable from its success: nothing was signalled, `SO_REUSEPORT` let the bind succeed anyway, and the result was two processes serving one port with neither of them told. Said at start-up rather than folded into the shutdown report, because by then the operator has already gone away believing the handover happened.
            # No `status=`: that field selects from `STATUS_PREFIXES`, which has no warning tier, and an unrecognised value falls to `[....]` — the dimmed prefix meaning "a request has just started". Left off, the level itself reaches `LEVEL_PREFIXES` and renders `[WARN]`.
            get_logger(LIFECYCLE_LOGGER).warning(
                f"--restart found no predecessor to take over from: {lookup.reason}; no handover happened, and another process may still be serving this port"
            )
    elif lookup.entry is not None and not options.force_write_pidfile:
        # Refused rather than overwritten. Overwriting is exactly what left a live process unfindable: a second start claimed the record on its way up and unlinked it on its way down, after which no `--restart` could locate the one still serving. A start that means to replace that process says `--restart`; one that means to run beside it anyway says `--force-write-pidfile` and accepts that the record will name the newcomer.
        # What this does *not* do is settle ownership. It compares against what the file said a moment ago and writes later, from the serving hook — two starts racing each other can both read an empty record and both go on. What it catches is the ordinary case of two starts one after another, where the gap is a human's and the window is milliseconds. Real atomic ownership needs serialisation between processes, which this is not.
        # The listener is released first. It is bound by this point, and scope exit alone does not free it: the exception keeps its traceback, the traceback keeps this frame, and the frame keeps `listeners` — so for as long as any caller holds the exception, the port stays held.
        listeners.close()
        raise PidfileError(
            f"{pidfile} still records pid {lookup.entry.pid}, which is running; "
            f"pass --restart to take over from it, or --force-write-pidfile to claim the record anyway"
        )
    elif (recorded := read_pidfile(pidfile)) is not None and not recorded.start_token:
        # A record naming a process but carrying no identity to check it against. The refusal above cannot fire, because nothing can confirm that pid is still the process that wrote this — and refusing on an unverifiable claim would lock the port out wherever `/proc` is unavailable. So it is claimed, but not in silence: the one case this leaves open is a hand-written or foreign record whose process is in fact alive.
        get_logger(LIFECYCLE_LOGGER).warning(f"claiming {pidfile}: {lookup.reason}")

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
    signalled: int | None = None

    if on_observable is not None:
        on_observable(adapter.connection_count)

    async def announce() -> None:
        nonlocal announced, signalled
        # Recorded only once accepting, so the file never names a process that cannot serve.
        write_pidfile(pidfile)
        announced = True
        # Only what was actually delivered is reported. `signal_restart` returns False when the process it pinned turned out to have exited between the lookup and the signal, and recording the intent instead would have the outcome claim a handover that never reached anybody. No warning for that case: a predecessor that left on its own is not one still holding the port.
        if predecessor is not None and signal_restart(predecessor):
            signalled = predecessor.pid

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
        signalled_predecessor=signalled,
    )
