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
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from app.lifecycle.pidfile import live_predecessor, read_pidfile

SRC = Path(__file__).resolve().parents[2] / "src"


def child_script() -> str:
    return textwrap.dedent(
        """
        import asyncio, os
        from pathlib import Path
        from fastapi import FastAPI
        from app.lifecycle.entry import StandaloneOptions, run_standalone

        app = FastAPI()

        async def live():
            return {"status": "ok"}

        app.add_api_route("/health/liveness", live)

        async def main():
            options = StandaloneOptions(
                host="127.0.0.1",
                port=int(os.environ["PORT"]),
                cleanup_timeout=5,
                pidfile=Path(os.environ["PIDFILE"]),
                restart=os.environ.get("RESTART") == "1",
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


def start_child(port: int, pidfile: Path, *, restart: bool = False) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env.update({"PYTHONPATH": str(SRC), "PORT": str(port), "PIDFILE": str(pidfile)})
    if restart:
        env["RESTART"] = "1"
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


def request_liveness(port: int, timeout: float = 5.0) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as client:
        client.sendall(b"GET /health/liveness HTTP/1.1\r\nHost: t\r\nConnection: close\r\n\r\n")
        chunks: list[bytes] = []
        while True:
            piece = client.recv(4096)
            if not piece:
                return b"".join(chunks)
            chunks.append(piece)


def stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


@pytest.fixture
def pidfile(tmp_path: Path) -> Path:
    return tmp_path / "standalone.pid"


def test_a_real_process_serves_and_records_its_pid(pidfile: Path) -> None:
    port = free_port()
    child = start_child(port, pidfile)
    try:
        pid = wait_until_serving(pidfile)
        assert pid == child.pid
        assert b"200 OK" in request_liveness(port)
    finally:
        stop(child)


def test_sigterm_reaches_the_ladder_in_a_real_process(pidfile: Path) -> None:
    """Proves the handlers are installed, which every in-process test bypasses."""
    port = free_port()
    child = start_child(port, pidfile)
    try:
        wait_until_serving(pidfile)
        child.send_signal(signal.SIGTERM)
        stdout, _ = child.communicate(timeout=20)
        assert "STOPPED DRAINING" in stdout
        assert child.returncode == 0
    finally:
        stop(child)


def test_the_pidfile_is_removed_when_the_process_stops(pidfile: Path) -> None:
    port = free_port()
    child = start_child(port, pidfile)
    try:
        wait_until_serving(pidfile)
        child.send_signal(signal.SIGTERM)
        child.communicate(timeout=20)
        assert pidfile.exists() is False
    finally:
        stop(child)


def test_a_replacement_takes_the_port_and_retires_its_predecessor(pidfile: Path) -> None:
    """The whole point of the restart: both processes hold the port during the handover.

    The successor binds under SO_REUSEPORT while the old one is still listening.
    Only then does it signal, so the port never stops answering.
    """
    port = free_port()
    first = start_child(port, pidfile)
    second: subprocess.Popen[str] | None = None
    try:
        first_pid = wait_until_serving(pidfile)
        assert live_predecessor(pidfile) == first_pid

        second = start_child(port, pidfile, restart=True)
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
    finally:
        stop(first)
        if second is not None:
            stop(second)


def test_a_start_without_restart_leaves_the_incumbent_alone(pidfile: Path) -> None:
    # The negative control: SO_REUSEPORT lets both bind, but nothing is signalled without --restart.
    port = free_port()
    first = start_child(port, pidfile)
    second: subprocess.Popen[str] | None = None
    try:
        wait_until_serving(pidfile)
        second = start_child(port, pidfile)
        time.sleep(1.5)
        assert first.poll() is None, "the incumbent must not be retired without --restart"
    finally:
        stop(first)
        if second is not None:
            stop(second)
