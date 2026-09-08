"""What actually happens to the half-sent request in test_a_half_sent_request_holds_the_drain.

The child fixture serves a bare FastAPI with a single GET route, so a POST to it is a routing
failure, not a handler that reads a body. This asks the running server directly.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path("tests/integration").resolve()))
from test_standalone_process import child_script, free_port  # noqa: E402

SRC = str(Path("src").resolve())


def main() -> int:
    port = free_port()
    with tempfile.TemporaryDirectory() as tmp:
        pidfile = Path(tmp) / "pid"
        env = os.environ.copy()
        env.update({"PYTHONPATH": SRC, "PORT": str(port), "PIDFILE": str(pidfile)})
        child = subprocess.Popen(
            [sys.executable, "-c", child_script()],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            for _ in range(200):
                if pidfile.exists():
                    break
                time.sleep(0.1)
            sock = socket.create_connection(("127.0.0.1", port), timeout=10)
            sock.sendall(
                b"POST /health/liveness HTTP/1.1\r\nHost: localhost\r\n"
                b"Content-Type: application/json\r\nContent-Length: 400\r\n\r\n"
                b'{"partial":'
            )
            # No signal yet. Does the server answer the half-sent request on its own?
            sock.settimeout(3.0)
            try:
                answer = sock.recv(4096)
            except TimeoutError:
                answer = b"<nothing: the server is still waiting for the body>"
            print(f"[probe] server's answer before any signal: {answer[:160]!r}", flush=True)
            sock.close()
        finally:
            child.terminate()
            child.communicate(timeout=15)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
