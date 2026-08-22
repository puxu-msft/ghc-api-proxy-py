"""The pidfile that `--restart` uses to find its predecessor.

The failure that matters is not "the file was missing".
It is signalling a process that merely inherited a recycled PID.
The identity check therefore gets the most attention here.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.lifecycle.pidfile import (
    PidfileEntry,
    PidfileError,
    live_predecessor,
    look_up_predecessor,
    process_start_token,
    read_pidfile,
    remove_pidfile,
    signal_restart,
    write_entry,
    write_pidfile,
)


def test_a_written_file_records_this_process(tmp_path: Path) -> None:
    path = tmp_path / "standalone.pid"
    entry = write_pidfile(path)
    assert entry.pid == os.getpid()
    assert read_pidfile(path) == entry


def test_the_first_line_is_a_bare_pid(tmp_path: Path) -> None:
    # Ordinary tooling reads the first line; the identity token must not break that.
    path = tmp_path / "standalone.pid"
    write_pidfile(path)
    assert path.read_text(encoding="utf-8").splitlines()[0] == str(os.getpid())


def test_writing_creates_the_parent_directory(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "run" / "standalone.pid"
    write_pidfile(path)
    assert path.is_file()


def test_writing_leaves_no_temporary_behind(tmp_path: Path) -> None:
    path = tmp_path / "standalone.pid"
    write_pidfile(path)
    assert [item.name for item in tmp_path.iterdir()] == ["standalone.pid"]


def test_a_missing_file_has_no_predecessor(tmp_path: Path) -> None:
    assert live_predecessor(tmp_path / "absent.pid") is None
    assert read_pidfile(tmp_path / "absent.pid") is None


@pytest.mark.parametrize("content", ["", "\n", "not-a-pid\n", "0\n", "-5\n"])
def test_a_malformed_file_is_treated_as_no_predecessor(tmp_path: Path, content: str) -> None:
    path = tmp_path / "standalone.pid"
    path.write_text(content, encoding="utf-8")
    assert read_pidfile(path) is None
    assert live_predecessor(path) is None


def test_our_own_pid_is_not_a_predecessor(tmp_path: Path) -> None:
    # A restart must not signal itself.
    path = tmp_path / "standalone.pid"
    write_pidfile(path)
    assert live_predecessor(path) is None


def test_a_pid_recorded_without_an_identity_token_is_refused(tmp_path: Path) -> None:
    """A bare PID cannot be verified, and unverified must not mean trusted.

    This is the whole point.
    An old-format or hand-written file names a PID that some unrelated process may now own.
    """
    path = tmp_path / "standalone.pid"
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]) as other:
        try:
            path.write_text(f"{other.pid}\n", encoding="utf-8")
            assert read_pidfile(path) == PidfileEntry(pid=other.pid, start_token="")
            assert live_predecessor(path) is None
        finally:
            other.kill()


def test_a_recycled_pid_is_not_mistaken_for_the_predecessor(tmp_path: Path) -> None:
    """The dangerous case: the PID is alive, but it is somebody else.

    Simulated by recording a live process under a start token that is not its own.
    That is exactly what a stale file looks like once the kernel hands the PID to a new process.
    """
    path = tmp_path / "standalone.pid"
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]) as other:
        try:
            genuine = process_start_token(other.pid)
            assert genuine, "this test needs /proc"
            path.write_text(f"{other.pid}\n{int(genuine) + 1}\n", encoding="utf-8")
            assert live_predecessor(path) is None
        finally:
            other.kill()


def test_a_live_matching_process_is_the_predecessor(tmp_path: Path) -> None:
    # The positive control for the two refusals above: a genuine record must be accepted.
    path = tmp_path / "standalone.pid"
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]) as other:
        try:
            write_pidfile(path, other.pid)
            found = live_predecessor(path)
            assert found is not None and found.pid == other.pid
        finally:
            other.kill()


def test_a_dead_process_is_not_a_predecessor(tmp_path: Path) -> None:
    path = tmp_path / "standalone.pid"
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    write_pidfile(path, other.pid)
    other.kill()
    other.wait()
    assert live_predecessor(path) is None


def test_a_missing_file_says_there_is_no_record(tmp_path: Path) -> None:
    """`--restart` states an intention, so its refusal has to be sayable.

    The entry alone cannot carry that: `None` reads the same whether the file was absent, unparsable, or naming a process that has since died, and those tell an operator very different things about what just happened.
    """
    lookup = look_up_predecessor(tmp_path / "absent.pid")
    assert lookup.entry is None
    assert "no record" in lookup.reason


def test_an_unparsable_file_is_distinguished_from_an_absent_one(tmp_path: Path) -> None:
    path = tmp_path / "standalone.pid"
    path.write_text("not a pid\n", encoding="utf-8")
    assert "unreadable record" in look_up_predecessor(path).reason


def test_a_record_without_a_token_says_it_cannot_be_verified(tmp_path: Path) -> None:
    path = tmp_path / "standalone.pid"
    path.write_text("4242\n", encoding="utf-8")
    reason = look_up_predecessor(path).reason
    assert "no identity to verify" in reason
    # The pid is named, because an operator reading this wants to know who was claimed.
    assert "4242" in reason


def test_a_dead_process_says_the_record_is_stale(tmp_path: Path) -> None:
    path = tmp_path / "standalone.pid"
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    write_pidfile(path, other.pid)
    other.kill()
    other.wait()
    reason = look_up_predecessor(path).reason
    # Deliberately not "has exited": the same branch is taken when `/proc` cannot be read, where the process may still be alive and it is only the check that failed.
    assert "no longer matches" in reason
    assert str(other.pid) in reason


def test_a_found_predecessor_carries_no_reason(tmp_path: Path) -> None:
    # The positive control: the reason field must stay empty when there is nothing to explain, or "did it find one" becomes unanswerable from the lookup alone.
    path = tmp_path / "standalone.pid"
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]) as other:
        try:
            write_pidfile(path, other.pid)
            lookup = look_up_predecessor(path)
            assert lookup.entry is not None and lookup.entry.pid == other.pid
            assert lookup.reason == ""
        finally:
            other.kill()


def test_the_predecessor_receives_the_restart_signal(tmp_path: Path) -> None:
    """SIGUSR2 reaches the recorded process, and it is the restart signal rather than a stop."""
    script = (
        "import signal, sys, time\n"
        "signal.signal(signal.SIGUSR2, lambda *_: sys.exit(7))\n"
        "time.sleep(30)\n"
    )
    path = tmp_path / "standalone.pid"
    with subprocess.Popen([sys.executable, "-c", script]) as other:
        try:
            write_pidfile(path, other.pid)
            time.sleep(0.5)
            found = live_predecessor(path)
            assert found is not None and found.pid == other.pid
            assert signal_restart(found) is True
            assert other.wait(timeout=5) == 7
        finally:
            if other.poll() is None:
                other.kill()


def test_a_recycled_pid_is_not_signalled(tmp_path: Path) -> None:
    """The failure this whole mechanism exists to prevent: signalling somebody else.

    A live process wearing a PID we recorded earlier must not be signalled just for holding the number. Standing in for the recycled process is a live one whose recorded token is wrong, which is the same thing as far as the check is concerned — and it would die of SIGUSR2 if signalled.
    """
    del tmp_path
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]) as other:
        try:
            time.sleep(0.5)
            impostor = PidfileEntry(pid=other.pid, start_token="1")
            assert signal_restart(impostor) is False
            time.sleep(0.5)
            assert other.poll() is None, "an unrelated process was signalled"
        finally:
            other.kill()


def test_signal_restart_refuses_an_unverifiable_entry() -> None:
    # No token means the claim cannot be checked at all, so nothing may be signalled on it.
    with pytest.raises(PidfileError):
        signal_restart(PidfileEntry(pid=os.getpid(), start_token=""))


def test_signal_restart_uses_sigusr2() -> None:
    from app.lifecycle.pidfile import RESTART_SIGNAL

    assert RESTART_SIGNAL is signal.SIGUSR2


def test_removal_only_happens_when_the_file_is_still_ours(tmp_path: Path) -> None:
    # A replacement has already rewritten the file; removing it would strand the live process.
    path = tmp_path / "standalone.pid"
    write_pidfile(path, os.getpid() + 1)
    assert remove_pidfile(path) is False
    assert path.is_file()


def test_removal_happens_when_the_file_records_us(tmp_path: Path) -> None:
    path = tmp_path / "standalone.pid"
    write_pidfile(path)
    assert remove_pidfile(path) is True
    assert path.exists() is False


def test_removing_an_absent_file_reports_false(tmp_path: Path) -> None:
    assert remove_pidfile(tmp_path / "absent.pid") is False


def test_restoring_a_record_keeps_its_original_token(tmp_path: Path) -> None:
    """Putting a record back must not re-derive its identity from whoever holds the PID now.

    A predecessor that exited during a failed handover may have had its PID reused. Recomputing the token would then certify the stranger, and the next `--restart` would signal it — the very accident the token exists to prevent. Writing the original bytes leaves it provably stale instead, which the identity check refuses.
    """
    path = tmp_path / "standalone.pid"
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]) as other:
        try:
            time.sleep(0.5)
            stale = PidfileEntry(pid=other.pid, start_token="1")
            write_entry(path, stale)

            assert read_pidfile(path) == stale
            assert live_predecessor(path) is None, "a stale token must not be re-certified"
        finally:
            other.kill()
