from __future__ import annotations

import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest


async def _control(path: Path, command: dict[str, object]) -> dict[str, object]:
    reader, writer = await asyncio.open_unix_connection(path)
    try:
        writer.write(json.dumps(command).encode() + b"\n")
        await writer.drain()
        return json.loads(await reader.readline())
    finally:
        writer.close()
        await writer.wait_closed()


async def _http_request(port: int, path: str) -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        writer.write(
            f"GET {path} HTTP/1.1\r\nHost: test\r\nConnection: close\r\n\r\n".encode()
        )
        await writer.drain()
        return await reader.read()
    finally:
        writer.close()
        await writer.wait_closed()


def _listener(family: socket.AddressFamily) -> socket.socket:
    listener = socket.socket(family, socket.SOCK_STREAM)
    if family == socket.AF_INET6:
        listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        listener.bind(("::1", 0))
    else:
        listener.bind(("127.0.0.1", 0))
    listener.listen(32)
    return listener


def _child_script() -> str:
    return textwrap.dedent(
        """
        import asyncio
        import os
        import socket
        from dataclasses import dataclass
        from pathlib import Path
        from fastapi import FastAPI
        from app.config.settings import AppSettings
        from app.lifecycle.rolling.generation.phases import GenerationLifecycle
        from app.lifecycle.rolling.runtime import RollingRuntime
        from app.socket_activation import ActivatedSocketSet, ExpectedListener

        @dataclass
        class State:
            generation_lifecycle: GenerationLifecycle
            dependencies_ready: bool = True
            approval_gate: None = None
            websocket_manager: None = None
            settings: AppSettings = AppSettings.model_validate(
                {"shutdown": {"drain_timeout": int(os.environ.get("DRAIN_TIMEOUT", "0"))}}
            )
            def readiness_checks(self):
                return {"ready": True}

        async def main():
            v4 = socket.socket(fileno=int(os.environ["V4_FD"]))
            v6 = socket.socket(fileno=int(os.environ["V6_FD"]))
            activated = ActivatedSocketSet(
                {"http-v4": v4, "http-v6": v6},
                [
                    ExpectedListener("http-v4", socket.AF_INET, "127.0.0.1", v4.getsockname()[1]),
                    ExpectedListener("http-v6", socket.AF_INET6, "::1", v6.getsockname()[1]),
                ],
            )
            app = FastAPI()
            lifecycle = GenerationLifecycle()
            app.state.runtime = State(lifecycle)
            async def live():
                return {"status": "ok"}
            app.add_api_route("/health/liveness", live)
            async def block():
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    print("OPERATION_CANCELLED", flush=True)
                    raise
            app.add_api_route("/block", block)
            runtime = RollingRuntime(
                app,
                activated,
                generation_id="g0000000000000001",
                release_id="test-release",
                control_path=Path(os.environ["CONTROL_PATH"]),
                notify_ready_fn=lambda: print("READY", flush=True),
                notify_stopping_fn=lambda: print("STOPPING", flush=True),
            )
            await runtime.run()
        asyncio.run(main())
        """
    )


def _start_child(
    tmp_path: Path,
    *,
    drain_timeout: int = 0,
) -> tuple[subprocess.Popen[str], socket.socket, socket.socket, Path]:
    ipv4 = _listener(socket.AF_INET)
    ipv6 = _listener(socket.AF_INET6)
    control = tmp_path / "generation.sock"
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
            "V4_FD": str(ipv4.fileno()),
            "V6_FD": str(ipv6.fileno()),
            "CONTROL_PATH": str(control),
            "DRAIN_TIMEOUT": str(drain_timeout),
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-c", _child_script()],
        env=env,
        pass_fds=(ipv4.fileno(), ipv6.fileno()),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return process, ipv4, ipv6, control


def _wait_for_line(process: subprocess.Popen[str], expected: str) -> None:
    assert process.stdout is not None
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        line = process.stdout.readline()
        if expected in line:
            return
    raise AssertionError(f"did not observe {expected!r}")


@pytest.mark.asyncio
async def test_real_usr_quiesce_resume_and_term_cleanup(tmp_path: Path) -> None:
    process, ipv4, ipv6, control = _start_child(tmp_path)
    try:
        _wait_for_line(process, "READY")
        ready = await _control(control, {"version": 1, "command": "status"})
        assert ready["phase"] == "ready_accepting"

        process.send_signal(signal.SIGUSR2)
        revision = ready["revision"]
        assert isinstance(revision, int)
        quiesced = await _control(
            control,
            {
                "version": 1,
                "command": "wait",
                "after_revision": revision,
                "timeout_ms": 2000,
            },
        )
        assert quiesced["phase"] == "quiescing"
        assert quiesced["accepting"] is False

        process.send_signal(signal.SIGUSR1)
        resumed = await _control(
            control,
            {
                "version": 1,
                "command": "wait",
                "after_revision": quiesced["revision"],
                "timeout_ms": 2000,
            },
        )
        assert resumed["phase"] == "ready_accepting"

        process.send_signal(signal.SIGTERM)
        _wait_for_line(process, "STOPPING")
        assert process.wait(timeout=5) == 0
        assert control.exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        ipv4.close()
        ipv6.close()
        control.unlink(missing_ok=True)
        control.with_name(control.name + ".lock").unlink(missing_ok=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("second_signal", "expected_code"),
    [(signal.SIGTERM, 143), (signal.SIGINT, 130)],
)
async def test_second_termination_signal_exits_immediately(
    tmp_path: Path,
    second_signal: signal.Signals,
    expected_code: int,
) -> None:
    process, ipv4, ipv6, control_path = _start_child(tmp_path)
    try:
        _wait_for_line(process, "READY")
        blocked = asyncio.create_task(_http_request(ipv4.getsockname()[1], "/block"))
        status: dict[str, object] = {}
        for _ in range(100):
            status = await _control(control_path, {"version": 1, "command": "status"})
            if status["active_operations"] == 1:
                break
            await asyncio.sleep(0.01)
        assert status["active_operations"] == 1
        process.send_signal(signal.SIGTERM)
        await asyncio.sleep(0.05)
        process.send_signal(second_signal)
        assert process.wait(timeout=5) == expected_code
        blocked.cancel()
        await asyncio.gather(blocked, return_exceptions=True)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        ipv4.close()
        ipv6.close()


@pytest.mark.asyncio
async def test_usr2_positive_timeout_cancels_real_http_operation(tmp_path: Path) -> None:
    process, ipv4, ipv6, control_path = _start_child(tmp_path, drain_timeout=1)
    try:
        _wait_for_line(process, "READY")
        blocked = asyncio.create_task(_http_request(ipv4.getsockname()[1], "/block"))
        status: dict[str, object] = {}
        for _ in range(100):
            status = await _control(control_path, {"version": 1, "command": "status"})
            if status["active_operations"] == 1:
                break
            await asyncio.sleep(0.01)
        assert status["active_operations"] == 1

        process.send_signal(signal.SIGUSR2)
        for _ in range(200):
            status = await _control(control_path, {"version": 1, "command": "status"})
            if status["active_operations"] == 0:
                break
            await asyncio.sleep(0.01)
        assert status["phase"] == "quiescing"
        assert status["active_operations"] == 0
        assert process.poll() is None
        response = await asyncio.wait_for(blocked, 2)
        assert b"200 OK" not in response
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        ipv4.close()
        ipv6.close()


@pytest.mark.asyncio
async def test_first_term_positive_timeout_cancels_real_http_operation_and_exits(
    tmp_path: Path,
) -> None:
    process, ipv4, ipv6, control_path = _start_child(tmp_path, drain_timeout=1)
    try:
        _wait_for_line(process, "READY")
        blocked = asyncio.create_task(_http_request(ipv4.getsockname()[1], "/block"))
        status: dict[str, object] = {}
        for _ in range(100):
            status = await _control(control_path, {"version": 1, "command": "status"})
            if status["active_operations"] == 1:
                break
            await asyncio.sleep(0.01)
        assert status["active_operations"] == 1
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 0
        response = await asyncio.wait_for(blocked, 2)
        assert b"200 OK" not in response
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        ipv4.close()
        ipv6.close()
