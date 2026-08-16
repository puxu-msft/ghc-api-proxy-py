"""The pidfile a directly-run process uses to find its predecessor.

`--restart` has to signal the process it is replacing.
The only thing it knows about that process is what the previous run left on disk.
A stale file must therefore be distinguishable from a live one.
The consequence of getting it wrong is signalling somebody else.

PIDs are recycled, so a bare PID is not an identity.
The file records the process start time alongside it, which the kernel never reuses for a PID.
Both must match before anything is signalled, and the match is made against a process already
pinned by a pidfd so that it cannot be replaced between the check and the signal.

The first line stays a bare PID so `cat` and the usual tooling still work.
The identity token is on the second line.
A file carrying only a PID counts as unverifiable, not as a match.

systemd and pm2 skip this mechanism entirely, per the spec.
"""

import ctypes
import os
import signal
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

RESTART_SIGNAL = signal.SIGUSR2

# `pidfd_send_signal`. Kernels since 5.x give new calls the same number on every architecture, and
# the number is only reached when CPython has no binding for it; the probe below proves it is right.
_SYS_PIDFD_SEND_SIGNAL = 424


class PidfileError(RuntimeError):
    """The pidfile could not be read or written."""


@dataclass(frozen=True, slots=True)
class PidfileEntry:
    pid: int
    start_token: str = ""

    def rendered(self) -> str:
        return f"{self.pid}\n{self.start_token}\n"


def process_start_token(pid: int) -> str:
    """A value that distinguishes this process from a later one with the same PID.

    Returns an empty string where /proc is unavailable, which callers must treat as "cannot verify"
    rather than as "verified".
    """
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return ""
    return _starttime_field(stat)


def _starttime_field(stat: str) -> str:
    """Field 22 of `/proc/<pid>/stat`, or an empty string when it cannot be read out."""
    # `comm` is parenthesised and may itself contain spaces, so fields are counted after it.
    try:
        fields = stat[stat.rindex(")") + 2 :].split()
        return fields[19]
    except ValueError, IndexError:
        return ""


def read_pidfile(path: Path) -> PidfileEntry | None:
    """Parse the pidfile, or return None when it is absent or unusable.

    An unreadable or malformed file is not worth stopping a start-up for.
    The outcome is the same as having no predecessor, which is a normal first run.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    lines = content.splitlines()
    if not lines:
        return None
    try:
        pid = int(lines[0].strip())
    except ValueError:
        return None
    if pid <= 0:
        return None
    token = lines[1].strip() if len(lines) > 1 else ""
    return PidfileEntry(pid=pid, start_token=token)


def write_pidfile(path: Path, pid: int | None = None) -> PidfileEntry:
    """Record this process, replacing whatever was there."""
    resolved = os.getpid() if pid is None else pid
    return write_entry(path, PidfileEntry(pid=resolved, start_token=process_start_token(resolved)))


def write_entry(path: Path, entry: PidfileEntry) -> PidfileEntry:
    """Write an already-formed record, token and all.

    Restoring a record must not go through `write_pidfile`: that re-derives the token from whoever
    holds the PID *now*, so putting back a process that has since exited would mint a fresh identity
    for its replacement and certify a stranger. Writing the original bytes keeps the entry either
    correct or provably stale, which the identity check can act on.

    Written to a temporary name and renamed, so a reader never sees a half-written file.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{entry.pid}.tmp")
        temporary.write_text(entry.rendered(), encoding="utf-8")
        temporary.replace(path)
    except OSError as error:
        raise PidfileError(f"cannot write pidfile {path}: {error}") from error
    return entry


def live_predecessor(path: Path) -> PidfileEntry | None:
    """The entry recorded in `path`, if that exact process is still running.

    Returns None when the file is missing or the process is gone.
    Also when the recorded identity does not match the process currently holding that PID.

    The whole entry is returned rather than the PID, because the PID alone is not enough to signal
    safely later: `signal_restart` re-checks the token against the process it has pinned, and this
    answer can be minutes old by the time it does.
    """
    entry = read_pidfile(path)
    if entry is None or entry.pid == os.getpid():
        return None
    if not entry.start_token:
        # Nothing to compare against, so the claim cannot be verified. Refuse rather than guess.
        return None
    if entry.start_token != process_start_token(entry.pid):
        return None
    return entry


def signal_restart(entry: PidfileEntry) -> bool:
    """Tell the predecessor a replacement is up, and report whether it was still there.

    SIGUSR2 means "from a smooth restart", so the receiver drains rather than dropping its work.

    Checking the identity and then calling `os.kill` would be two decisions about two possibly
    different processes: the predecessor can exit in between and its PID be handed to something
    else, which would then receive the signal. So the order here is pin, verify, signal.

    The pin is a directory descriptor on `/proc/<pid>`, which refers to that one process rather than
    to the number. Should the process exit and its PID be handed out again, the descriptor does not
    follow: reads through it and signals sent through it fail instead of reaching the newcomer. Both
    later steps go through it, so neither can be answered by a stranger.
    """
    if not entry.start_token:
        raise PidfileError(f"refusing to signal {entry.pid}: no recorded identity to verify")
    send_signal = _pidfd_signaller()
    if send_signal is None:
        raise PidfileError("smooth restart needs pidfd support, which this platform lacks")

    try:
        handle = os.open(f"/proc/{entry.pid}", os.O_RDONLY | os.O_DIRECTORY)
    except FileNotFoundError, ProcessLookupError:
        return False
    except OSError as error:
        raise PidfileError(f"cannot signal process {entry.pid}: {error}") from error

    try:
        if _start_token_of(handle) != entry.start_token:
            # The PID now belongs to someone else. Signalling it is exactly the accident to avoid.
            return False
        send_signal(handle, RESTART_SIGNAL)
    except ProcessLookupError:
        return False
    except OSError as error:
        raise PidfileError(f"cannot signal process {entry.pid}: {error}") from error
    finally:
        os.close(handle)
    return True


def _start_token_of(handle: int) -> str:
    """The start time of the process `handle` refers to, read through the descriptor itself.

    Reading `/proc/<pid>/stat` by path again would reintroduce the very substitution the pin exists
    to prevent.
    """
    try:
        stat_fd = os.open("stat", os.O_RDONLY, dir_fd=handle)
    except OSError:
        return ""
    try:
        stat = os.read(stat_fd, 8192).decode("utf-8", "replace")
    finally:
        os.close(stat_fd)
    return _starttime_field(stat)


@cache
def _pidfd_signaller() -> Callable[[int, int], None] | None:
    """How to signal a pinned process, or None where that cannot be done at all.

    CPython only exposes `signal.pidfd_send_signal` when the interpreter was built against headers
    that had it, which is not the same question as whether the running kernel supports it — this
    project's own interpreter is a build that lacks the binding on a kernel that has the call. So
    the syscall is reached directly as a fallback, and the fallback proves itself against this
    process before it is trusted with somebody else's.
    """
    native = getattr(signal, "pidfd_send_signal", None)
    if native is not None:
        return lambda handle, sig: native(handle, sig)

    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long

    def send(handle: int, sig: int) -> None:
        ctypes.set_errno(0)
        code = libc.syscall(
            ctypes.c_long(_SYS_PIDFD_SEND_SIGNAL),
            ctypes.c_int(handle),
            ctypes.c_int(sig),
            None,
            ctypes.c_uint(0),
        )
        if code != 0:
            errno = ctypes.get_errno()
            raise OSError(errno, os.strerror(errno))

    try:
        probe = os.open(f"/proc/{os.getpid()}", os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return None
    try:
        # Signal 0 delivers nothing and only checks that the call is the one we think it is.
        send(probe, 0)
    except OSError:
        return None
    finally:
        os.close(probe)
    return send


def remove_pidfile(path: Path, pid: int | None = None) -> bool:
    """Remove the file only when it still records us, and report whether it did.

    A replacement has already overwritten it by the time this process finishes.
    Deleting it then would leave the live process without a pidfile.
    """
    resolved = os.getpid() if pid is None else pid
    entry = read_pidfile(path)
    if entry is None or entry.pid != resolved:
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True
