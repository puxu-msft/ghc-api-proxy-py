"""The pidfile a directly-run process uses to find its predecessor.

`--restart` has to signal the process it is replacing.
The only thing it knows about that process is what the previous run left on disk.
A stale file must therefore be distinguishable from a live one.
The consequence of getting it wrong is signalling somebody else.

PIDs are recycled, so a bare PID is not an identity.
The file records the process start time alongside it, which the kernel never reuses for a PID.
Both must match before anything is signalled.

The first line stays a bare PID so `cat` and the usual tooling still work.
The identity token is on the second line.
A file carrying only a PID counts as unverifiable, not as a match.

systemd and pm2 skip this mechanism entirely, per the spec.
"""

import os
import signal
from dataclasses import dataclass
from pathlib import Path

RESTART_SIGNAL = signal.SIGUSR2


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
    # `comm` is parenthesised and may itself contain spaces, so fields are counted after it.
    try:
        fields = stat[stat.rindex(")") + 2 :].split()
        return fields[19]
    except (ValueError, IndexError):
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
    """Record this process, replacing whatever was there.

    Written to a temporary name and renamed, so a reader never sees a half-written file.
    """
    resolved = os.getpid() if pid is None else pid
    entry = PidfileEntry(pid=resolved, start_token=process_start_token(resolved))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{resolved}.tmp")
        temporary.write_text(entry.rendered(), encoding="utf-8")
        temporary.replace(path)
    except OSError as error:
        raise PidfileError(f"cannot write pidfile {path}: {error}") from error
    return entry


def live_predecessor(path: Path) -> int | None:
    """The PID recorded in `path`, if that exact process is still running.

    Returns None when the file is missing or the process is gone.
    Also when the recorded identity does not match the process currently holding that PID.
    That last case is the one that matters.
    Without it a recycled PID would make an unrelated process the target of a restart signal.
    """
    entry = read_pidfile(path)
    if entry is None or entry.pid == os.getpid():
        return None
    if not entry.start_token:
        # Nothing to compare against, so the claim cannot be verified. Refuse rather than guess.
        return None
    if entry.start_token != process_start_token(entry.pid):
        return None
    return entry.pid


def signal_restart(pid: int) -> None:
    """Tell the predecessor a replacement is up.

    SIGUSR2 means "from a smooth restart", so the receiver drains rather than dropping its work.
    """
    try:
        os.kill(pid, RESTART_SIGNAL)
    except OSError as error:
        raise PidfileError(f"cannot signal process {pid}: {error}") from error


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
