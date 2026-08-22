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
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from shlex import split
from threading import Thread
from typing import ClassVar

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
