"""The stand-alone lifecycle in a real process, driven by real signals.

Every other test calls `receive_signal` directly, which bypasses handler installation entirely.
Only a real process can show that SIGTERM and SIGUSR2 reach the ladder at all.
The same goes for the pidfile naming something a successor can find, and for two processes really
overlapping on one port.

The child builds a minimal app rather than the production one.
What is under test is the lifecycle, not the proxy's dependencies.
"""

import os
import signal
import socket
import ssl
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from app.config.paths import standalone_pidfile_path, user_data_path
from app.lifecycle.pidfile import (
    PidfileEntry,
    live_predecessor,
    read_pidfile,
    write_entry,
    write_pidfile,
)

SRC = Path(__file__).resolve().parents[2] / "src"


def child_script() -> str:
    return textwrap.dedent(
        """
        import asyncio, os
        from pathlib import Path
        from fastapi import FastAPI, Request
        from app.lifecycle.entry import StandaloneOptions, run_standalone
        from app.observability.logging import setup_logging

        # Configured here because the lifecycle now says something at start-up that a test needs to read, and an unconfigured structlog would not put it anywhere this process's captured streams can see.
        setup_logging(log_format="text", log_level="INFO")

        app = FastAPI()

        async def live():
            return {"status": "ok"}

        async def swallow(request: Request):
            # Reads the whole body, so a client that announces more than it sends leaves this handler genuinely waiting. A route that never touches the body cannot express that: Starlette answers it off the headers alone.
            marker = os.environ.get("ENTERED_MARKER")
            if marker:
                # A line per arrival, appended and flushed. The alternative — a test that waits and concludes from silence that the handler is in — cannot tell "waiting for the body" from "not scheduled yet", and those two lead to opposite verdicts.
                with open(marker, "a") as handle:
                    handle.write("entered\\n")
                    handle.flush()
            body = await request.body()
            return {"read": len(body)}

        app.add_api_route("/health/liveness", live)
        app.add_api_route("/swallow", swallow, methods=["POST"])

        async def main():
            configured_tls_mode = False
            tls_material = None
            requested_tls_mode = os.environ.get("TLS_MODE")
            if requested_tls_mode is not None:
                from app.lifecycle.tls import generate_self_signed

                configured_tls_mode = True if requested_tls_mode == "true" else requested_tls_mode
                tls_material = generate_self_signed(Path(os.environ["TLS_DIR"]))
            pidfile_dir_env = os.environ.get("PIDFILE_DIR")
            options = StandaloneOptions(
                host="127.0.0.1",
                port=int(os.environ["PORT"]),
                tls_mode=configured_tls_mode,
                tls_material=tls_material,
                cleanup_timeout=5,
                # Left unset when the test wants the default location, which is the one derived from XDG_DATA_HOME.
                pidfile_dir=Path(pidfile_dir_env) if pidfile_dir_env else None,
                restart=os.environ.get("RESTART") == "1",
                force_write_pidfile=os.environ.get("FORCE_WRITE_PIDFILE") == "1",
            )
            print("STARTING", flush=True)
            outcome = await run_standalone(app, options)
            print(f"STOPPED {outcome.report.stage.name}", flush=True)

        asyncio.run(main())
        """
    )


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def start_child(
    port: int,
    pidfile_dir: Path | None,
    *,
    restart: bool = False,
    tls_mode: bool | str | None = None,
    entered_marker: Path | None = None,
    data_home: Path | None = None,
    force_write_pidfile: bool = False,
) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env.update({"PYTHONPATH": str(SRC), "PORT": str(port)})
    if pidfile_dir is not None:
        env["PIDFILE_DIR"] = str(pidfile_dir)
    else:
        # No explicit directory, so the child resolves the default one under `XDG_DATA_HOME`, which is what the port-naming is about. `data_home` keeps that inside the test's own tree instead of the developer's.
        env.pop("PIDFILE_DIR", None)
    if data_home is not None:
        env["XDG_DATA_HOME"] = str(data_home)
    if entered_marker is not None:
        env["ENTERED_MARKER"] = str(entered_marker)
    if restart:
        env["RESTART"] = "1"
    if force_write_pidfile:
        env["FORCE_WRITE_PIDFILE"] = "1"
    if tls_mode is not None:
        assert pidfile_dir is not None, "the TLS material directory is derived from the pidfile directory"
        env["TLS_MODE"] = "true" if tls_mode is True else str(tls_mode)
        env["TLS_DIR"] = str(pidfile_dir / "tls")
    return subprocess.Popen(
        [sys.executable, "-c", child_script()],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def wait_until_serving(pidfile: Path, timeout: float = 20.0) -> int:
    """The pidfile is written from the serving hook, so its presence means the port is open."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entry = read_pidfile(pidfile)
        if entry is not None:
            return entry.pid
        time.sleep(0.05)
    raise AssertionError(f"child never started serving: {pidfile}")


def wait_until_recorded(pidfile: Path, pid: int, timeout: float = 20.0) -> None:
    """Wait for the record to name `pid`, when some other record is already in place.

    `wait_until_serving` reads presence, which only means "started" when the file was absent to begin with. Where a predecessor's or a leftover's entry is already there, presence is true from the outset and would be mistaken for the new process having started.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entry = read_pidfile(pidfile)
        if entry is not None and entry.pid == pid:
            return
        time.sleep(0.05)
    recorded = read_pidfile(pidfile)
    raise AssertionError(
        f"{pidfile} never came to name pid {pid}; it holds {recorded.pid if recorded else 'nothing'}"
    )


def request_liveness(port: int, timeout: float = 5.0) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as client:
        client.sendall(b"GET /health/liveness HTTP/1.1\r\nHost: t\r\nConnection: close\r\n\r\n")
        return read_response(client)


def request_tls_liveness(port: int, timeout: float = 5.0) -> bytes:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with (
        socket.create_connection(("127.0.0.1", port), timeout=timeout) as raw_client,
        context.wrap_socket(raw_client, server_hostname="localhost") as client,
    ):
        client.sendall(b"GET /health/liveness HTTP/1.1\r\nHost: t\r\nConnection: close\r\n\r\n")
        return read_response(client)


def read_response(client: socket.socket) -> bytes:
    chunks: list[bytes] = []
    while True:
        piece = client.recv(4096)
        if not piece:
            return b"".join(chunks)
        chunks.append(piece)


def wait_for_arrivals(marker: Path, expected: int, timeout: float = 10.0) -> None:
    """Block until `expected` requests have reached the `/swallow` handler.

    A positive signal from the handler itself, rather than the test inferring from silence that the request must be in. Silence also covers "the event loop has not got to it yet", and those two states send the shutdown down different paths.
    """
    deadline = time.monotonic() + timeout
    arrived = 0
    while time.monotonic() < deadline:
        arrived = marker.read_text().count("entered") if marker.exists() else 0
        if arrived >= expected:
            return
        time.sleep(0.02)
    raise AssertionError(f"only {arrived} of {expected} requests reached the handler")


def stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


@pytest.fixture
def pidfile_dir(tmp_path: Path) -> Path:
    """The directory a child records itself in; the name inside it belongs to the code.

    A test that needs the file asks `standalone_pidfile_path` for it rather than spelling it, so that a change to the naming rule reaches these tests instead of leaving them asserting against a copy of the old one.
    """
    return tmp_path / "run"


def test_a_real_process_serves_and_records_its_pid(pidfile_dir: Path) -> None:
    port = free_port()
    pidfile = standalone_pidfile_path(port, pidfile_dir)
    child = start_child(port, pidfile_dir)
    try:
        pid = wait_until_serving(pidfile)
        assert pid == child.pid
        assert b"200 OK" in request_liveness(port)
    finally:
        stop(child)


def test_both_mode_serves_http_and_https_on_one_port(pidfile_dir: Path) -> None:
    port = free_port()
    pidfile = standalone_pidfile_path(port, pidfile_dir)
    child = start_child(port, pidfile_dir, tls_mode="both")
    try:
        wait_until_serving(pidfile)
        assert b"200 OK" in request_liveness(port)
        assert b"200 OK" in request_tls_liveness(port)
    finally:
        stop(child)


def test_tls_only_naturally_closes_a_plaintext_connection(pidfile_dir: Path) -> None:
    port = free_port()
    pidfile = standalone_pidfile_path(port, pidfile_dir)
    child = start_child(port, pidfile_dir, tls_mode=True)
    try:
        wait_until_serving(pidfile)
        try:
            response = request_liveness(port)
        except (ConnectionError, OSError):
            response = b""
        assert response == b""
    finally:
        stop(child)


def test_plaintext_only_does_not_complete_a_tls_handshake(pidfile_dir: Path) -> None:
    port = free_port()
    pidfile = standalone_pidfile_path(port, pidfile_dir)
    child = start_child(port, pidfile_dir)
    try:
        wait_until_serving(pidfile)
        with pytest.raises((ssl.SSLError, ConnectionError, OSError)):
            request_tls_liveness(port)
    finally:
        stop(child)


def test_sigterm_reaches_the_ladder_in_a_real_process(pidfile_dir: Path) -> None:
    """Proves the handlers are installed, which every in-process test bypasses."""
    port = free_port()
    pidfile = standalone_pidfile_path(port, pidfile_dir)
    child = start_child(port, pidfile_dir)
    try:
        wait_until_serving(pidfile)
        child.send_signal(signal.SIGTERM)
        stdout, _ = child.communicate(timeout=20)
        assert "STOPPED DRAINING" in stdout
        assert child.returncode == 0
    finally:
        stop(child)


def test_a_half_sent_request_holds_the_drain_until_the_operator_escalates(pidfile_dir: Path) -> None:
    """A request still arriving is a real request, and the drain is right to wait for it.

    This pins that on purpose. The module docstring rules the drain unbounded because a second wall-clock limit would cut off legitimate work while the operator still has escalation available, and a client that has not finished sending is no different: nothing here can know whether the rest is one packet away. What was wrong was never the waiting — it was that the display said nothing, because the proxy used to register a request only after reading its body. It registers on arrival now, so the footer shows it as `(resolving)` with a climbing clock for exactly as long as this test keeps it waiting.

    The route has to read the body for any of that to be true, and the wait has to be observed before the signal rather than assumed. Sent at a route that answers off the headers alone, this scenario used to hold the drain for a quite different reason — the request never reached a handler at all, and parked at the admission barrier instead, which is the deadlock `stop_admitting` exists to end. `test_a_pooled_client_that_races_the_signal_is_answered_rather_than_wedging_the_process` keeps that scenario, with the expectation it should have had.

    No upstream is involved and none is needed: the request never gets far enough to route.
    """
    port = free_port()
    pidfile = standalone_pidfile_path(port, pidfile_dir)
    marker = pidfile_dir / "entered"
    child = start_child(port, pidfile_dir, entered_marker=marker)
    held: list[socket.socket] = []
    try:
        wait_until_serving(pidfile)
        for _ in range(2):
            sock = socket.create_connection(("127.0.0.1", port), timeout=10)
            # Announces more than it sends, so the server is still waiting on `receive` when the signal lands.
            sock.sendall(
                b"POST /swallow HTTP/1.1\r\nHost: localhost\r\n"
                b"Content-Type: application/json\r\nContent-Length: 400\r\n\r\n"
                b'{"partial":'
            )
            held.append(sock)

        # The handlers are in, and waiting, before anything is signalled. Without this the signal races the request and what holds the drain is no longer the thing under test.
        wait_for_arrivals(marker, 2)

        child.send_signal(signal.SIGTERM)
        # An unobstructed drain here finishes well inside a second, so a process still running at three is waiting on these two rather than merely slow.
        time.sleep(3.0)
        assert child.poll() is None, "the drain gave up on requests that were still arriving"

        # The escalation the docstring points at, and the only thing that should end this.
        child.send_signal(signal.SIGTERM)
        stdout, _ = child.communicate(timeout=15)
        assert "STOPPED INTERRUPTING" in stdout
    finally:
        for sock in held:
            sock.close()
        stop(child)


def test_a_pooled_client_that_races_the_signal_is_answered_rather_than_wedging_the_process(
    pidfile_dir: Path,
) -> None:
    """The incident itself, in a real process under a real signal, with the right expectation.

    This is the scenario `test_a_half_sent_request_holds_the_drain_until_the_operator_escalates` used to run: send, then signal at once, with nothing synchronising the two. Deliberately unsynchronised, because the race is the point — the signal lands first, the request reaches the barrier after admission has already been shut, and before the fix it waited there for a resume that a shutdown never performs. The whole process then sat at rung 1 until the operator escalated, which is what was reported from production.

    It kept passing back then only because "still running at three seconds" was the very symptom. The correct expectation is the opposite one, and this is the only place in the suite aimed at this deadlock in a real process under a real signal — the in-process tests reach the same code, but the incident happened here.

    **A probabilistic guard, and worth knowing which way.** The race it depends on is the one being tested, so how often it fires depends on what broke. Measured over ten isolated runs each: clean code 0/10 (it raises no false alarms), the whole of `stop_admitting` removed 10/10, the deadlock mechanism revived on its own 4/10, the refusal alone removed 2/10. So one green run does not mean the guard held, and one red run is always real. Treat it as a net that catches a returning deadlock eventually rather than immediately, and do not read a single pass as coverage.
    """
    port = free_port()
    pidfile = standalone_pidfile_path(port, pidfile_dir)
    child = start_child(port, pidfile_dir)
    held: list[socket.socket] = []
    try:
        wait_until_serving(pidfile)
        for _ in range(2):
            sock = socket.create_connection(("127.0.0.1", port), timeout=10)
            sock.sendall(
                b"POST /health/liveness HTTP/1.1\r\nHost: localhost\r\n"
                b"Content-Type: application/json\r\nContent-Length: 400\r\n\r\n"
                b'{"partial":'
            )
            held.append(sock)
        child.send_signal(signal.SIGTERM)

        # Nothing legitimate is in flight: this route answers off its headers, so whatever the race decides, no handler is waiting on anything.
        stdout, stderr = child.communicate(timeout=15)
        assert child.returncode == 0
        assert "STOPPED DRAINING" in stdout, "one signal should have been enough"
        # The deadlock's other symptom, and the one an operator sees first. It only appears once the escalation cancels the parked requests, so a process that exits at rung 1 cannot produce it.
        assert "Exception in ASGI application" not in stderr
    finally:
        for sock in held:
            sock.close()
        stop(child)


def test_the_pidfile_is_removed_when_the_process_stops(pidfile_dir: Path) -> None:
    port = free_port()
    pidfile = standalone_pidfile_path(port, pidfile_dir)
    child = start_child(port, pidfile_dir)
    try:
        wait_until_serving(pidfile)
        child.send_signal(signal.SIGTERM)
        child.communicate(timeout=20)
        assert pidfile.exists() is False
    finally:
        stop(child)


def test_a_replacement_takes_the_port_and_retires_its_predecessor(pidfile_dir: Path) -> None:
    """The whole point of the restart: both processes hold the port during the handover.

    The successor binds under SO_REUSEPORT while the old one is still listening.
    Only then does it signal, so the port never stops answering.
    """
    port = free_port()
    pidfile = standalone_pidfile_path(port, pidfile_dir)
    first = start_child(port, pidfile_dir)
    second: subprocess.Popen[str] | None = None
    try:
        first_pid = wait_until_serving(pidfile)
        found = live_predecessor(pidfile)
        assert found is not None and found.pid == first_pid

        second = start_child(port, pidfile_dir, restart=True)
        # The pidfile now names the successor, which is how we know it took over.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            entry = read_pidfile(pidfile)
            if entry is not None and entry.pid == second.pid:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("successor never recorded itself")

        # The predecessor was asked to retire, and did so by draining rather than being killed.
        stdout, _ = first.communicate(timeout=20)
        assert "STOPPED DRAINING" in stdout
        assert first.returncode == 0

        # The port still answers, now from the successor.
        assert b"200 OK" in request_liveness(port)

        # The successor found a real predecessor, so it must not have complained about missing one. A warning that also fires on the happy path teaches the operator to scroll past it, which costs more than saying nothing would.
        second.send_signal(signal.SIGTERM)
        successor_said = "".join(second.communicate(timeout=20))
        assert "found no predecessor" not in successor_said, successor_said
    finally:
        stop(first)
        if second is not None:
            stop(second)


def test_a_start_without_restart_refuses_to_erase_the_incumbents_record(pidfile_dir: Path) -> None:
    """A second start on the same port is refused rather than allowed to claim the record.

    This used to be permitted, and permitting it is what left a serving process unfindable: the newcomer overwrote the entry on its way up and unlinked it on its way down, after which no `--restart` could locate the one still serving. `SO_REUSEPORT` means the bind itself cannot object, so the refusal has to come from the record.

    The incumbent is untouched either way — no signal is sent, and it never learns this happened. What changed is that the newcomer stops instead of quietly taking the record with it.
    """
    port = free_port()
    pidfile = standalone_pidfile_path(port, pidfile_dir)
    first = start_child(port, pidfile_dir)
    second: subprocess.Popen[str] | None = None
    try:
        first_pid = wait_until_serving(pidfile)

        second = start_child(port, pidfile_dir)
        try:
            stdout, stderr = second.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            # A refused start exits at once. Still running means it was allowed through, and saying so beats letting a bare `TimeoutExpired` stand in for the diagnosis.
            raise AssertionError(
                "the second start was not refused: it is still serving, and the record is now its own"
            ) from None
        said = stdout + stderr
        assert second.returncode != 0, said
        assert "still records pid" in said, said
        assert str(first_pid) in said, said
        # Both ways out are named, because a refusal that does not say what to do instead is one the operator works around with the nearest blunt instrument.
        assert "--restart" in said, said
        assert "--force-write-pidfile" in said, said

        # The incumbent is alive and still findable — the point of refusing at all.
        assert first.poll() is None, "the incumbent must not be retired without --restart"
        surviving = read_pidfile(pidfile)
        assert surviving is not None and surviving.pid == first_pid

        # And no handover warning: the newcomer never asked for one. A warning that fires here would teach the operator to scroll past the one that matters.
        assert "found no predecessor" not in said, said
    finally:
        stop(first)
        if second is not None:
            stop(second)


def test_force_write_pidfile_claims_the_record_anyway(pidfile_dir: Path) -> None:
    """The escape hatch, and what it costs.

    Someone who means to run a second instance beside the first can say so. The record then names the newcomer, which is precisely the state the refusal exists to prevent — so this is worth being able to reach deliberately and impossible to reach by accident.
    """
    port = free_port()
    pidfile = standalone_pidfile_path(port, pidfile_dir)
    first = start_child(port, pidfile_dir)
    second: subprocess.Popen[str] | None = None
    try:
        first_pid = wait_until_serving(pidfile)

        second = start_child(port, pidfile_dir, force_write_pidfile=True)
        wait_until_recorded(pidfile, second.pid)

        assert second.poll() is None, "the forced start must actually serve"
        assert first.poll() is None, "forcing the record must not disturb the incumbent"
        assert first_pid != second.pid
    finally:
        stop(first)
        if second is not None:
            stop(second)


def test_a_record_whose_process_has_gone_does_not_block_a_start(pidfile_dir: Path) -> None:
    """The refusal must not be over-broad, and this is the cheap way to get it wrong.

    A crashed or SIGKILLed process leaves its record behind — nothing removes it on the way out. If the check were "a file is here" rather than "a live process with a matching identity is named in it", that leftover would lock the port out of use until somebody deleted the file by hand, and the first thing an operator would reach for is `--force-write-pidfile`, which is the habit this refusal must not create.
    """
    port = free_port()
    pidfile = standalone_pidfile_path(port, pidfile_dir)
    departed = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    write_pidfile(pidfile, departed.pid)
    departed.kill()
    departed.wait(timeout=5)

    child = start_child(port, pidfile_dir)
    try:
        # Not `wait_until_serving`: the departed process's record is still on disk, so presence would be true immediately and would hand back its pid rather than this child's.
        wait_until_recorded(pidfile, child.pid)
        assert b"200 OK" in request_liveness(port)
    finally:
        stop(child)


def test_a_record_whose_pid_was_recycled_does_not_block_a_start(pidfile_dir: Path) -> None:
    """The other half: the pid is alive, but it is not the process that wrote the record.

    PIDs are reused, which is the whole reason the second line exists. A refusal that stopped at "is something running under this number" would be wrong exactly when the number has been handed to an unrelated process — and on a busy machine that is not rare.
    """
    port = free_port()
    pidfile = standalone_pidfile_path(port, pidfile_dir)
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]) as stranger:
        try:
            # A live pid carrying somebody else's start time, which is what a recycled pid looks like from the outside. Deliberately not a plausible tick count: field 22 of `/proc/<pid>/stat` counts ticks since boot, so a number like 999999 is roughly three hours' uptime at 100Hz and could in principle be somebody's real value.
            write_entry(pidfile, PidfileEntry(pid=stranger.pid, start_token="not-a-real-start-time"))

            child = start_child(port, pidfile_dir)
            try:
                # Not `wait_until_serving`: a record is already present, so presence would be true from the outset and would read as the new process having started.
                wait_until_recorded(pidfile, child.pid)
                assert b"200 OK" in request_liveness(port)
            finally:
                stop(child)
        finally:
            stranger.kill()


def test_an_unverifiable_record_is_claimed_but_not_in_silence(pidfile_dir: Path) -> None:
    """A record naming a process with nothing to check the claim against.

    The refusal cannot fire here: without the identity line, nothing can confirm that pid is still the process that wrote this, and refusing on an unverifiable claim would lock the port out anywhere `/proc` is unreadable. So it is claimed — but this is the one remaining shape of the original incident (a live process losing its record), so it does not happen quietly.

    Reachable mainly through a hand-written file or a foreign format; `write_pidfile` always records an identity on Linux.
    """
    port = free_port()
    pidfile = standalone_pidfile_path(port, pidfile_dir)
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]) as holder:
        try:
            # First line only, the way `cat`-friendly pidfiles have always been written.
            write_entry(pidfile, PidfileEntry(pid=holder.pid))

            child = start_child(port, pidfile_dir)
            try:
                wait_until_recorded(pidfile, child.pid)
                child.send_signal(signal.SIGTERM)
                stdout, stderr = child.communicate(timeout=20)
                said = stdout + stderr
                assert "[WARN]" in said, said
                assert "claiming" in said, said
                assert "no identity to verify" in said, said
                assert str(holder.pid) in said, said
            finally:
                stop(child)
        finally:
            holder.kill()


def test_a_restart_that_finds_no_predecessor_says_so(pidfile_dir: Path) -> None:
    """The cell this matrix was missing, and the one where intention and outcome diverge.

    `--restart` means "take over from the one already there". When the record naming that process is gone, nothing is signalled — and `SO_REUSEPORT` then lets the bind succeed anyway, so the operator gets two processes serving one port with no error, no failed bind, and until now no line of output either. A silent success and a silent failure looked identical.
    """
    port = free_port()
    pidfile = standalone_pidfile_path(port, pidfile_dir)
    # `restart` is asked for against a pidfile that was never written, which is exactly the state a throwaway run on another port used to leave behind.
    child = start_child(port, pidfile_dir, restart=True)
    try:
        wait_until_serving(pidfile)
        # It still serves: the warning reports the handover, it does not refuse the start.
        assert b"200 OK" in request_liveness(port)

        child.send_signal(signal.SIGTERM)
        stdout, stderr = child.communicate(timeout=20)
        said = stdout + stderr
        assert "found no predecessor" in said, said
        assert "no record" in said, said
        # Rendered at the warning tier. An explicit `status=` would select from `STATUS_PREFIXES`, which has no warning entry, and an unrecognised value falls through to `[....]` — the dimmed prefix that means "a request has just started". The text would still be there, and the one line reporting a failed handover would be dressed as routine.
        assert "[WARN]" in said, said
    finally:
        stop(child)


def test_the_pidfile_names_the_port_the_kernel_chose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default path is derived from the bound address, not from the port that was asked for.

    Those two are the same number everywhere else, and today they are the same number on every route the CLI can take: `--port` is constrained to 1..65535, `server.port` likewise, and `--fd` goes through `serve_inherited`, which owns no pidfile at all. So this exercises `run_standalone`'s own call surface rather than a reachable CLI path.

    Kept anyway, because it is the only thing standing between `address[1]` and somebody simplifying it to `options.port` — a change nothing else here would notice, and one that would name the file after a port no successor could find the moment either constraint is relaxed.
    """
    data_home = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    child = start_child(0, None, data_home=data_home)
    try:
        directory = user_data_path()
        deadline = time.monotonic() + 20
        found: list[Path] = []
        while time.monotonic() < deadline:
            found = sorted(directory.glob("standalone-*.pid")) if directory.exists() else []
            if found:
                break
            time.sleep(0.05)
        else:
            raise AssertionError(f"no pidfile appeared under {directory}")

        assert len(found) == 1, found
        chosen = int(found[0].stem.removeprefix("standalone-"))
        # The negative assertion is the whole point: 0 is what was requested, never what was bound.
        assert chosen != 0
        assert not (directory / "standalone-0.pid").exists()
        # And the name is not merely plausible — that port is the one answering.
        assert b"200 OK" in request_liveness(chosen)
    finally:
        stop(child)


def test_a_run_on_another_port_leaves_the_incumbent_its_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression this naming exists for, end to end.

    One shared default file made every `start` a claimant to the same record regardless of port: the throwaway overwrote the incumbent's entry as it came up and unlinked it as it went down. The incumbent kept serving and never heard about it, and the next `--restart` had nothing to find. Both children here resolve the *default* path — passing one explicitly would test the very thing that was never broken.

    The expected paths come from the production function rather than being formatted here. Spelling them out locally would make the "two ports, two files" assertion compare two strings this test built itself, which no change to the code under test could ever falsify.
    """
    data_home = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    incumbent_port = free_port()
    throwaway_port = free_port()
    # Constrains the fixture, not the code: two `bind(0)` probes may hand back the same port.
    assert incumbent_port != throwaway_port
    incumbent_pidfile = standalone_pidfile_path(incumbent_port)
    throwaway_pidfile = standalone_pidfile_path(throwaway_port)

    incumbent = start_child(incumbent_port, None, data_home=data_home)
    throwaway: subprocess.Popen[str] | None = None
    try:
        incumbent_pid = wait_until_serving(incumbent_pidfile)

        throwaway = start_child(throwaway_port, None, data_home=data_home)
        wait_until_serving(throwaway_pidfile)
        # Two ports, two files. Under the old shared name both children resolved to one path, and this second start had already destroyed the first one's record by now.
        assert incumbent_pidfile != throwaway_pidfile

        throwaway.send_signal(signal.SIGTERM)
        throwaway.communicate(timeout=20)
        assert throwaway_pidfile.exists() is False, "a departing run must clean up after itself"

        # The point of the whole change: the incumbent is still findable by the process that comes next.
        surviving = read_pidfile(incumbent_pidfile)
        assert surviving is not None and surviving.pid == incumbent_pid
        assert live_predecessor(incumbent_pidfile) is not None
    finally:
        stop(incumbent)
        if throwaway is not None:
            stop(throwaway)
