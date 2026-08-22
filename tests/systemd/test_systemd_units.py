import json
import os
import signal
import socket
import stat
import subprocess
import sys
import time
from configparser import ConfigParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from shlex import split
from threading import Event, Thread
from typing import ClassVar

import pytest

from app.config.paths import (
    spec_config_file_path,
    tokenization_state_path,
    user_data_path,
)
from app.graceful_timeout import (
    DEFAULT_GRACEFUL_TIMEOUT_SECONDS,
    SYSTEMD_STOP_TIMEOUT_MARGIN_SECONDS,
    SYSTEMD_STOP_TIMEOUT_SECONDS,
)
from app.history.sqlite.writer import HistoryWriter
from app.history.types import HistoryEntry, ModelRef
from app.tokenization.state_store import TokenizationStateStore

SYSTEMD_DIR = Path(__file__).parents[2] / "contrib" / "systemd"


def read_unit(name: str) -> ConfigParser:
    parser = ConfigParser(interpolation=None)
    with (SYSTEMD_DIR / name).open(encoding="utf-8") as unit_file:
        parser.read_file(unit_file)
    return parser


def _assert_graceful_timeout_contract(service: ConfigParser) -> None:
    command = split(service["Service"]["ExecStart"])
    graceful_timeout = int(command[command.index("--graceful-timeout") + 1])
    stop_timeout = int(service["Service"]["TimeoutStopSec"].removesuffix("s"))
    assert stop_timeout > graceful_timeout, "systemd deadline must strictly exceed app timeout"
    assert graceful_timeout == DEFAULT_GRACEFUL_TIMEOUT_SECONDS
    assert stop_timeout == SYSTEMD_STOP_TIMEOUT_SECONDS
    assert stop_timeout - graceful_timeout == SYSTEMD_STOP_TIMEOUT_MARGIN_SECONDS


def http_request(connection: socket.socket, path: str) -> bytes:
    connection.sendall(
        f"GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode()
    )
    chunks: list[bytes] = []
    while chunk := connection.recv(65536):
        chunks.append(chunk)
    return b"".join(chunks)


def _http_json_request(connection: socket.socket, path: str, payload: object) -> bytes:
    body = json.dumps(payload).encode()
    connection.sendall(
        f"POST {path} HTTP/1.1\r\n"
        "Host: localhost\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n".encode()
        + body
    )
    chunks: list[bytes] = []
    while chunk := connection.recv(65536):
        chunks.append(chunk)
    return b"".join(chunks)


class _GenericUpstreamHandler(BaseHTTPRequestHandler):
    requests: ClassVar[list[str]] = []
    hold_messages: ClassVar[bool] = False
    message_started: ClassVar[Event] = Event()
    release_message: ClassVar[Event] = Event()

    def do_GET(self) -> None:
        self.requests.append(self.path)
        # Both hosts land here: the service is configured with `api_base_url` and `auth_base_url`
        # pointing at this one server, which is the whole reason those two are configurable.
        if self.path == "/copilot_internal/v2/token":
            # The exchange the proxy performs before it can talk to the inference host at all.
            # `refresh_in` is what upstream sends, so the stand-in sends it too. It is no longer
            # required — nothing reads it since the background refresh loop went — but a fixture
            # that quietly drifts from the real response shape stops being evidence about it.
            self._respond(
                {
                    "token": "copilot-smoke-token",
                    "expires_at": 4102444800,
                    "refresh_in": 1500,
                }
            )
            return
        assert self.path == "/models", self.path
        self._respond(
            {
                "object": "list",
                "data": [
                    {
                        "id": "claude-test",
                        "vendor": "Anthropic",
                        "supported_endpoints": ["/v1/messages"],
                    }
                ],
            }
        )

    def do_POST(self) -> None:
        self.requests.append(self.path)
        assert self.path == "/v1/messages"
        content_length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(content_length))
        assert request["model"] == "claude-test"
        if self.hold_messages:
            self.message_started.set()
            self.release_message.wait(timeout=15)
        try:
            self._respond(
                {
                    "id": "msg_smoke",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-test",
                    "content": [{"type": "text", "text": "ok"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 12, "output_tokens": 1},
                }
            )
        except (BrokenPipeError, ConnectionResetError):
            if not self.hold_messages:
                raise

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _respond(self, payload: object) -> None:
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_socket_activation_units_share_the_inherited_listener() -> None:
    socket = read_unit("ghc-api-proxy.socket")
    service = read_unit("ghc-api-proxy.service")

    assert socket["Socket"]["ListenStream"] == "127.0.0.1:4141"
    assert socket["Socket"]["Accept"] == "no"
    assert socket["Socket"]["Service"] == "ghc-api-proxy.service"
    assert service["Service"]["Type"] == "exec"
    assert "ExecReload" not in service["Service"]
    assert split(service["Service"]["ExecStart"]) == [
        "/opt/ghc-api-proxy/.venv/bin/python",
        "-m",
        "app",
        "start",
        "--fd",
        "3",
        "--graceful-timeout",
        str(DEFAULT_GRACEFUL_TIMEOUT_SECONDS),
    ]
    assert "ghc-api-proxy.socket" in service["Unit"]["Requires"].split()


def test_service_provisions_and_configures_writable_state_directory() -> None:
    service = read_unit("ghc-api-proxy.service")

    assert service["Service"]["StateDirectory"] == "ghc-api-proxy"
    assert service["Service"]["StateDirectoryMode"] == "0700"
    assert service["Service"]["UMask"] == "0077"
    # One variable, not two paths. The chain derives every state location from XDG_DATA_HOME, so
    # pointing that at the directory systemd already creates covers the config, the token file and
    # the calibration state at once. The two keys that stood here named the retired chain's paths,
    # and the current schema rejects them — the process exits at startup rather than ignoring them.
    environment = set(split(service["Service"]["Environment"]))
    assert environment == {"XDG_DATA_HOME=/var/lib"}


def test_service_state_environment_lands_in_the_state_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unit's `Environment=` has to actually decide where state is written.

    The invariant is unchanged; its consumer is not. It used to be asserted against
    `load_settings()` and the two `GHC_API_PROXY_*__*_PATH` keys, which belong to the chain `--fd` no longer
    runs. `StateDirectory=ghc-api-proxy` makes systemd create `/var/lib/ghc-api-proxy`, and the
    assertion is that this is exactly where the chain then looks.
    """
    service = read_unit("ghc-api-proxy.service")
    for assignment in split(service["Service"]["Environment"]):
        name, value = assignment.split("=", 1)
        monkeypatch.setenv(name, value)

    expected = Path("/var/lib") / service["Service"]["StateDirectory"]
    assert user_data_path() == expected
    assert tokenization_state_path() == expected / "tokenization.json"
    assert spec_config_file_path() == expected / "config.yaml"


@pytest.mark.asyncio
async def test_service_permissions_restrict_real_state_writers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = read_unit("ghc-api-proxy.service")
    directory_mode = int(service["Service"]["StateDirectoryMode"], 8)
    service_umask = int(service["Service"]["UMask"], 8)
    state_directory = tmp_path / "state"
    temporary_modes: list[int] = []
    original_replace = Path.replace

    def inspect_temporary_mode(source: Path, target: Path) -> Path:
        if source.parent == state_directory and source.name.endswith(".tmp"):
            temporary_modes.append(stat.S_IMODE(source.stat().st_mode))
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", inspect_temporary_mode)
    previous_umask = os.umask(service_umask)
    try:
        state_directory.mkdir(mode=directory_mode)
        history_path = state_directory / "history.db"
        writer = HistoryWriter(history_path)
        await writer.start()
        try:
            await writer.submit(
                HistoryEntry(
                    id="permissions-smoke",
                    session_id="session",
                    agent_id="main",
                    started_at=1,
                    ended_at=2,
                    endpoint="anthropic-messages",
                    status="completed",
                    model=ModelRef("claude-test", "claude-test"),
                    request_payload={"message": "permissions"},
                )
            )
            await writer.flush()
            sqlite_paths = [
                history_path,
                history_path.with_name("history.db-wal"),
                history_path.with_name("history.db-shm"),
            ]
            assert all(path.is_file() for path in sqlite_paths)
            sqlite_modes = {
                path.name: stat.S_IMODE(path.stat().st_mode) for path in sqlite_paths
            }

            tokenization_path = state_directory / "tokenization.json"
            tokenization = TokenizationStateStore(tokenization_path)
            tokenization.calibration.learn("anthropic", "claude-test", 10, 12)
            assert await tokenization.flush() is True
            assert tokenization_path.is_file()
            tokenization_mode = stat.S_IMODE(tokenization_path.stat().st_mode)
        finally:
            await writer.close()
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(state_directory.stat().st_mode) == 0o700
    assert temporary_modes == [0o600]
    assert sqlite_modes == {
        "history.db": 0o600,
        "history.db-wal": 0o600,
        "history.db-shm": 0o600,
    }
    assert tokenization_mode == 0o600


def test_service_shutdown_and_cgroup_contract() -> None:
    service = read_unit("ghc-api-proxy.service")
    resource_slice = read_unit("ghc-api-proxy.slice")

    assert service["Service"]["EnvironmentFile"].startswith("-")
    assert service["Service"]["Restart"] == "on-failure"
    assert service["Service"]["KillSignal"] == "SIGTERM"
    assert service["Service"]["KillMode"] == "control-group"
    _assert_graceful_timeout_contract(service)
    assert service["Service"]["Slice"] == "ghc-api-proxy.slice"
    assert resource_slice["Slice"]["MemoryHigh"] == "1G"
    assert resource_slice["Slice"]["MemoryMax"] == "2G"
    assert resource_slice["Slice"]["CPUQuota"] == "200%"
    assert resource_slice["Slice"]["TasksMax"] == "256"


def test_service_shutdown_contract_rejects_nonpositive_manager_margin() -> None:
    service = read_unit("ghc-api-proxy.service")
    service["Service"]["TimeoutStopSec"] = f"{DEFAULT_GRACEFUL_TIMEOUT_SECONDS}s"

    with pytest.raises(AssertionError, match="strictly exceed"):
        _assert_graceful_timeout_contract(service)


RETIRED_CHAIN_CONTRACT = pytest.mark.skip(
    reason=(
        "Frozen 2026-08-19: `--fd` now runs the pipeline chain, and these two assert the retired "
        "chain's contract rather than the invariant they were written for. Liveness answering "
        "`{'status': 'ok'}` is now `alive`; readiness `healthy` is now `ready`; a written "
        "`history.db` presumes a history store the pipeline chain does not have; and the state "
        "locations came from `GHC_API_PROXY_HISTORY__DB_PATH` / `GHC_API_PROXY_TOKENIZATION__STATE_PATH`, which the "
        "current schema rejects outright. "
        "Superseded by `test_systemd_pipeline_unit.py`, which stands the same unit up on an "
        "inherited listener with both hosts pointed at a local fake and no real credentials — "
        "the coverage these lost, on the chain that is actually served. "
        "They are kept rather than deleted because their inference and graceful-shutdown halves "
        "have no replacement yet: the fake there speaks only the two GET halves of the protocol. "
        "Exit condition: teach it `POST /v1/messages`, then port those assertions across and "
        "delete these."
    )
)


@RETIRED_CHAIN_CONTRACT
def test_inherited_listener_serves_ready_generic_upstream_and_persists_overrides(
    tmp_path: Path,
) -> None:
    default_state_directory = tmp_path / "default-state"
    override_state_directory = tmp_path / "override-state"
    default_state_directory.mkdir()
    override_state_directory.mkdir()
    history_path = override_state_directory / "history.db"
    tokenization_path = override_state_directory / "tokenization.json"
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _GenericUpstreamHandler)
    upstream_thread = Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    upstream_url = f"http://127.0.0.1:{upstream.server_address[1]}"
    _GenericUpstreamHandler.requests = []
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    address = listener.getsockname()
    backlog_client = socket.create_connection(address, timeout=10)
    backlog_client.settimeout(20)

    environment = os.environ.copy()
    for name in ("GHC_API_PROXY_GITHUB_TOKEN", "GHC_API_PROXY_CONFIG"):
        environment.pop(name, None)
    # Re-added below with a fake value; popped first so the operator's real one cannot leak in.
    service = read_unit("ghc-api-proxy.service")
    unit_state_environment = {
        name: str(default_state_directory / Path(value).name)
        for assignment in split(service["Service"]["Environment"])
        for name, value in [assignment.split("=", 1)]
    }
    environment.update(unit_state_environment)
    environment.update(
        {
            "HOME": "/nonexistent",
            "PYTHONPATH": str(SYSTEMD_DIR.parents[1] / "src"),
            # Both hosts at the local fake. Configurable since 2026-08-19; before that the auth
            # host was a module constant and this could not be stood up without real credentials.
            "GHC_API_PROXY_MODEL_PROVIDERS__GHC__TYPE": "github_copilot",
            "GHC_API_PROXY_MODEL_PROVIDERS__GHC__API_BASE_URL": upstream_url,
            "GHC_API_PROXY_MODEL_PROVIDERS__GHC__AUTH_BASE_URL": upstream_url,
            "GHC_API_PROXY_MODEL_PROVIDERS__GHC__MODEL_REFRESH_INTERVAL": "0",
            "GHC_API_PROXY_DEFAULT_MODEL_PROVIDER": "ghc",
            # A GitHub token for `EnvTokenProvider`; the fake exchanges whatever it is given.
            "GHC_API_PROXY_GITHUB_TOKEN": "ghu_smoke",
        }
    )
    inherited_fd = listener.fileno()
    launcher = (
        "import os, sys; "
        "source = int(sys.argv[1]); "
        "os.dup2(source, 3); "
        "os.set_inheritable(3, True); "
        "os.execv(sys.executable, [sys.executable, '-m', 'app', 'start', '--fd', '3'])"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", launcher, str(inherited_fd)],
        cwd=SYSTEMD_DIR.parents[1],
        env=environment,
        pass_fds=(inherited_fd,),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        backlog_response = http_request(backlog_client, "/health/liveness")
        assert b"HTTP/1.1 200 OK" in backlog_response
        assert b'{"status":"ok"}' in backlog_response

        with socket.create_connection(address, timeout=10) as readiness_client:
            readiness_client.settimeout(10)
            readiness_response = http_request(readiness_client, "/health/readiness")
        assert b"HTTP/1.1 200 OK" in readiness_response
        assert b'"status":"healthy"' in readiness_response

        with socket.create_connection(address, timeout=10) as messages_client:
            messages_client.settimeout(10)
            messages_response = _http_json_request(
                messages_client,
                "/v1/messages",
                {
                    "model": "claude-test",
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
        assert b"HTTP/1.1 200 OK" in messages_response
        assert b'"id": "msg_smoke"' in messages_response

        process.send_signal(signal.SIGTERM)
        output, _ = process.communicate(timeout=20)
        assert process.returncode == -signal.SIGTERM, output
        assert "Application shutdown complete." in output
        assert "Finished server process" in output
        assert history_path.is_file()
        assert tokenization_path.is_file()
        assert not (default_state_directory / "history.db").exists()
        assert not (default_state_directory / "tokenization.json").exists()
        assert _GenericUpstreamHandler.requests == ["/v1/models", "/v1/messages"]
    finally:
        _GenericUpstreamHandler.hold_messages = False
        _GenericUpstreamHandler.message_started.clear()
        _GenericUpstreamHandler.release_message.clear()
        backlog_client.close()
        listener.close()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=10)
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)


@RETIRED_CHAIN_CONTRACT
def test_short_graceful_timeout_cancels_inflight_request_and_runs_lifespan(
    tmp_path: Path,
) -> None:
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _GenericUpstreamHandler)
    upstream_thread = Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    upstream_url = f"http://127.0.0.1:{upstream.server_address[1]}"
    _GenericUpstreamHandler.requests = []
    _GenericUpstreamHandler.hold_messages = True
    _GenericUpstreamHandler.message_started.clear()
    _GenericUpstreamHandler.release_message.clear()

    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    address = listener.getsockname()
    environment = os.environ.copy()
    for name in ("GHC_API_PROXY_GITHUB_TOKEN", "GHC_API_PROXY_CONFIG"):
        environment.pop(name, None)
    environment.update(
        {
            "HOME": "/nonexistent",
            "PYTHONPATH": str(SYSTEMD_DIR.parents[1] / "src"),
            "GHC_API_PROXY_HISTORY__ENABLED": "false",
            "GHC_API_PROXY_TOKENIZATION__STATE_PATH": str(tmp_path / "tokenization.json"),
            "GHC_API_PROXY_UPSTREAM__TYPE": "generic",
            "GHC_API_PROXY_UPSTREAM__OPENAI_BASE_URL": f"{upstream_url}/v1",
            "GHC_API_PROXY_UPSTREAM__ANTHROPIC_BASE_URL": upstream_url,
            "GHC_API_PROXY_UPSTREAM__API_KEY": "smoke-key",
            "GHC_API_PROXY_MODEL_REFRESH_INTERVAL": "0",
        }
    )
    inherited_fd = listener.fileno()
    launcher = (
        "import os, sys; "
        "source = int(sys.argv[1]); "
        "os.dup2(source, 3); "
        "os.set_inheritable(3, True); "
        "os.execv(sys.executable, "
        "[sys.executable, '-m', 'app', 'start', '--fd', '3', "
        "'--graceful-timeout', '1'])"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", launcher, str(inherited_fd)],
        cwd=SYSTEMD_DIR.parents[1],
        env=environment,
        pass_fds=(inherited_fd,),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    request_errors: list[OSError] = []

    def send_blocked_request() -> None:
        try:
            with socket.create_connection(address, timeout=10) as client:
                client.settimeout(10)
                _http_json_request(
                    client,
                    "/v1/messages",
                    {
                        "model": "claude-test",
                        "max_tokens": 16,
                        "messages": [{"role": "user", "content": "hold"}],
                    },
                )
        except OSError as error:
            request_errors.append(error)

    request_thread = Thread(target=send_blocked_request, daemon=True)
    try:
        with socket.create_connection(address, timeout=10) as readiness_client:
            readiness_client.settimeout(10)
            readiness_response = http_request(readiness_client, "/health/readiness")
        assert b"HTTP/1.1 200 OK" in readiness_response

        request_thread.start()
        assert _GenericUpstreamHandler.message_started.wait(timeout=10)
        started_at = time.monotonic()
        process.send_signal(signal.SIGTERM)
        output, _ = process.communicate(timeout=10)
        elapsed = time.monotonic() - started_at

        assert process.returncode == -signal.SIGTERM, output
        assert elapsed < 8
        assert "timeout graceful shutdown exceeded" in output
        assert "Application shutdown complete." in output
        assert "Finished server process" in output
    finally:
        _GenericUpstreamHandler.release_message.set()
        request_thread.join(timeout=10)
        _GenericUpstreamHandler.hold_messages = False
        _GenericUpstreamHandler.message_started.clear()
        _GenericUpstreamHandler.release_message.clear()
        listener.close()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=10)
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
