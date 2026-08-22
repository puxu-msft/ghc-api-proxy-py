"""The unit in `contrib/systemd/` starting the chain it actually runs, with no real credentials.

This is what `auth_base_url` was made configurable for. Until 2026-08-19 the GitHub token exchange
was the module constant `app.model_provider.ghc_client.tokens.TOKEN_URL`, so a process could redirect its
inference calls at a local server and its three auth calls at nothing: the chain could not be
stood up end to end without a real GitHub token and the network, and `--fd` had no coverage at all.

Both hosts point at one fake here, which is the whole point — the exchange, the catalog and the
inference all land somewhere a test controls.

The two tests in `test_systemd_units.py` cover the same ground for the chain this unit no longer
runs; see their skip reason.
"""

import json
import os
import signal
import socket
import ssl
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from shlex import split
from threading import Thread
from typing import Any, ClassVar, TypedDict, cast

import pytest
from test_systemd_units import SYSTEMD_DIR, http_request, read_unit


class _CopilotFake(BaseHTTPRequestHandler):
    """Speaks the two GET halves of the Copilot protocol the chain needs before it is ready."""

    requests: ClassVar[list[str]] = []

    def log_message(self, format: str, *args: object) -> None:
        """Silenced: the request log would interleave with pytest's own output."""
        del format, args

    def do_GET(self) -> None:
        self.requests.append(self.path)
        if self.path == "/copilot_internal/v2/token":
            # `refresh_in` is what upstream sends, so the stand-in sends it too. It is no longer
            # required — nothing reads it since the background refresh loop went — but a fixture
            # that quietly drifts from the real response shape stops being evidence about it.
            self._respond(
                {"token": "copilot-smoke", "expires_at": 4102444800, "refresh_in": 1500}
            )
            return
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

    def _respond(self, body: dict[str, object]) -> None:
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


CASSETTE = Path(__file__).resolve().parents[1] / "int" / "cassettes" / "anthropic_to_responses_stream.json"


class _RecordedChunk(TypedDict):
    text: str


class _RecordedResponse(TypedDict):
    status: int
    headers: dict[str, str]
    chunks: list[_RecordedChunk]


class _CassetteUpstream(BaseHTTPRequestHandler):
    """Replays a recorded Copilot session, including the streaming half `_CopilotFake` lacks.

    `_CopilotFake` speaks the two GET halves by hand, which is enough to reach readiness and no further — `test_systemd_units.py` keeps two tests skipped for exactly that reason, with "teach it `POST /v1/messages`" as the stated exit condition. Replaying is used instead of hand-writing the third half because a stand-in for a streaming response encodes what we believe the upstream sends, and that belief is what hides defects; the chunk boundaries here are the ones that were recorded, which matters because delivery works a block at a time.
    """

    interactions: ClassVar[dict[tuple[str, str], _RecordedResponse]] = {}
    requests: ClassVar[list[str]] = []

    @classmethod
    def load(cls) -> None:
        cls.interactions = {}
        cls.requests = []
        recorded = cast(dict[str, Any], json.loads(CASSETTE.read_text(encoding="utf-8")))
        for interaction in cast(list[dict[str, Any]], recorded["interactions"]):
            request = cast(dict[str, str], interaction["request"])
            cls.interactions[(request["method"], request["path"])] = cast(
                _RecordedResponse, interaction["response"]
            )

    def log_message(self, format: str, *args: object) -> None:
        """Silenced: the request log would interleave with pytest's own output."""
        del format, args

    def do_GET(self) -> None:
        self._replay("GET")

    def do_POST(self) -> None:
        self._replay("POST")

    def _replay(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        path = self.path.split("?")[0]
        self.requests.append(f"{method} {path}")
        recorded = self.interactions.get((method, path))
        if recorded is None:
            self.send_error(404, f"nothing recorded for {method} {path}")
            return
        self.send_response(recorded["status"])
        for name, value in recorded["headers"].items():
            # Framing is this server's to decide; the recorded values describe the connection it was captured on.
            if name.lower() in {"transfer-encoding", "content-length", "connection"}:
                continue
            self.send_header(name, value)
        self.end_headers()
        for chunk in recorded["chunks"]:
            # One write per recorded chunk, flushed: collapsing them would hand the proxy a shape the upstream never produced.
            self.wfile.write(chunk["text"].encode())
            self.wfile.flush()


def _service_environment(state_directory: Path, upstream_url: str) -> dict[str, str]:
    """The unit's own `Environment=`, plus what points this run at the fake.

    Read from the unit rather than restated, so a unit that sets a key the schema rejects fails
    here. That is not hypothetical: it set two keys belonging to the retired chain, and the
    process exited at startup rather than ignoring them.
    """
    environment = os.environ.copy()
    for name in ("GHC_API_PROXY_GITHUB_TOKEN", "GHC_API_PROXY_CONFIG"):
        environment.pop(name, None)
    service = read_unit("ghc-api-proxy.service")
    for assignment in split(service["Service"]["Environment"]):
        name, value = assignment.split("=", 1)
        # The unit points XDG_DATA_HOME at the StateDirectory; here it points at a temp one.
        environment[name] = str(state_directory) if name == "XDG_DATA_HOME" else value
    environment.update(
        {
            "HOME": "/nonexistent",
            "PYTHONPATH": str(SYSTEMD_DIR.parents[1] / "src"),
            "GHC_API_PROXY_MODEL_PROVIDERS__GHC__TYPE": "github_copilot",
            "GHC_API_PROXY_MODEL_PROVIDERS__GHC__API_BASE_URL": upstream_url,
            "GHC_API_PROXY_MODEL_PROVIDERS__GHC__AUTH_BASE_URL": upstream_url,
            "GHC_API_PROXY_MODEL_PROVIDERS__GHC__MODEL_REFRESH_INTERVAL": "0",
            "GHC_API_PROXY_DEFAULT_MODEL_PROVIDER": "ghc",
            "GHC_API_PROXY_GITHUB_TOKEN": "ghu_smoke",
        }
    )
    return environment


def test_the_unit_starts_the_chain_on_an_inherited_listener_without_real_credentials(
    tmp_path: Path,
) -> None:
    state_directory = tmp_path / "state"
    state_directory.mkdir()
    _CopilotFake.requests = []
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _CopilotFake)
    Thread(target=upstream.serve_forever, daemon=True).start()
    upstream_url = f"http://127.0.0.1:{upstream.server_address[1]}"

    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    address = listener.getsockname()
    # Connected before the process exists: a socket-activated service must answer what was already
    # queued, which is the property socket activation is chosen for.
    backlog_client = socket.create_connection(address, timeout=10)
    backlog_client.settimeout(30)

    launcher = (
        "import os, sys; "
        "source = int(sys.argv[1]); "
        "os.dup2(source, 3); "
        "os.set_inheritable(3, True); "
        "os.execv(sys.executable, [sys.executable, '-m', 'app', 'start', '--fd', '3'])"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", launcher, str(listener.fileno())],
        cwd=SYSTEMD_DIR.parents[1],
        env=_service_environment(state_directory, upstream_url),
        pass_fds=(listener.fileno(),),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        backlog_response = http_request(backlog_client, "/health/liveness")
        assert b"HTTP/1.1 200 OK" in backlog_response
        assert b'{"status":"alive"}' in backlog_response

        with socket.create_connection(address, timeout=10) as readiness_client:
            readiness_client.settimeout(10)
            readiness = http_request(readiness_client, "/health/readiness")
        # Ready means the catalog loaded, which is the fact routing uses. The fake offers one
        # model, so anything else here means the exchange or the catalog fetch did not happen.
        assert b"HTTP/1.1 200 OK" in readiness
        assert b'"status":"ready"' in readiness
        assert b'"models":1' in readiness

        process.send_signal(signal.SIGTERM)
        output, _ = process.communicate(timeout=30)
        assert process.returncode == -signal.SIGTERM, output

        # The order is the contract: nothing can be asked of the inference host until the token
        # exchange has happened, because the catalog request carries the token it returns.
        assert _CopilotFake.requests == ["/copilot_internal/v2/token", "/models"]
        # No assertion on written state: the calibration store writes nothing when it has
        # learnt nothing, and this run learns nothing. What the unit's `Environment=` is worth
        # checking for is covered above — it is applied verbatim, so a key the schema rejects
        # would have stopped the process before readiness ever answered.
    finally:
        backlog_client.close()
        listener.close()
        upstream.shutdown()
        if process.poll() is None:
            process.kill()


def _tls_client(address: tuple[str, int], timeout: float = 15.0) -> ssl.SSLSocket:
    context = ssl.create_default_context()
    # The certificate is self-signed into the state directory. Whether it would satisfy a real client is a separate question this deployment does not ask; what is under test is that the port speaks TLS.
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    raw = socket.create_connection(address, timeout=timeout)
    client = context.wrap_socket(raw, server_hostname="localhost")
    client.settimeout(timeout)
    return client


def _post_json_over_tls(address: tuple[str, int], path: str, payload: object) -> bytes:
    body = json.dumps(payload).encode()
    with _tls_client(address) as client:
        client.sendall(
            f"POST {path} HTTP/1.1\r\n"
            "Host: localhost\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n".encode()
            + body
        )
        chunks: list[bytes] = []
        while chunk := client.recv(65536):
            chunks.append(chunk)
        return b"".join(chunks)


@pytest.mark.parametrize("mode", ["true", "both"])
def test_an_inherited_listener_serves_the_real_api_over_https(mode: str, tmp_path: Path) -> None:
    """The deployment target reading the TLS section it ships with, exercised on the route it exists for.

    Until 2026-08-22 `serve_inherited` did not look at `server.tls` at all, so a socket-activated service configured for TLS served plaintext and said nothing about it.

    Driven through `POST /v1/messages` rather than a health check. `/health/liveness` answers off its headers and returns a few bytes, so it shows a handshake completing and almost nothing else — not a request body being read, not the chain being entered, not a streamed reply being written back. Those are the parts that behave differently under TLS, and they are what this deployment actually carries.

    `both` is the shipped default and cannot be honoured here: two protocols on one port means reading the first byte of each accepted connection, which requires owning the accepts, and on this path uvicorn does. It answers HTTPS and says what it dropped, which is why both modes run the same request and only `both` expects a line about it.
    """
    state_directory = tmp_path / "state"
    state_directory.mkdir()
    _CassetteUpstream.load()
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _CassetteUpstream)
    Thread(target=upstream.serve_forever, daemon=True).start()
    upstream_url = f"http://127.0.0.1:{upstream.server_address[1]}"

    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    address = listener.getsockname()

    environment = _service_environment(state_directory, upstream_url)
    environment["GHC_API_PROXY_SERVER__TLS__MODE"] = mode

    launcher = (
        "import os, sys; "
        "source = int(sys.argv[1]); "
        "os.dup2(source, 3); "
        "os.set_inheritable(3, True); "
        "os.execv(sys.executable, [sys.executable, '-m', 'app', 'start', '--fd', '3'])"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", launcher, str(listener.fileno())],
        cwd=SYSTEMD_DIR.parents[1],
        env=environment,
        pass_fds=(listener.fileno(),),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        # Readiness rather than liveness as the gate: the catalog has to be loaded before a model name can route, and the cassette's `/models` is what supplies it.
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with _tls_client(address) as probe:
                    readiness = http_request(probe, "/health/readiness")
                if b'"status":"ready"' in readiness:
                    break
            except (ssl.SSLError, ConnectionError, OSError):
                # The listener is queued from the start, so a connection lands before the process has armed it; retry rather than read "not yet" as "not TLS".
                pass
            time.sleep(0.2)
        else:
            raise AssertionError("the inherited listener never became ready over TLS")

        response = _post_json_over_tls(
            address,
            "/v1/messages",
            {
                # The model the cassette was recorded against, and one of the twelve in its catalog advertising `/responses`. A `claude-*` name would route to the Anthropic passthrough instead, which is not the path this deployment is for.
                "model": "gpt-5.5",
                "max_tokens": 64,
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

        assert b"HTTP/1.1 200 OK" in response, (response[:400], _CassetteUpstream.requests)
        # The reply is Anthropic's stream, translated from the recorded Responses one. Asserting on
        # its events rather than on the status alone is what separates "the port answered" from
        # "a request body was read, the chain ran, and blocks came back".
        assert b"event: message_start" in response, response
        assert b"event: content_block_delta" in response, response
        assert b"event: message_stop" in response, response
        # And the upstream really was called over the recorded path, not short-circuited.
        assert "POST /responses" in _CassetteUpstream.requests, _CassetteUpstream.requests

        process.send_signal(signal.SIGTERM)
        output, _ = process.communicate(timeout=30)
        assert process.returncode == -signal.SIGTERM, output
        # Said, not silently dropped: `both` asks for something this path cannot give, and the operator's config file will keep saying `both` afterwards.
        if mode == "both":
            assert "cannot serve" in output, output
            assert "HTTPS only" in output, output
        else:
            assert "cannot serve" not in output, output
    finally:
        listener.close()
        upstream.shutdown()
        if process.poll() is None:
            process.kill()
