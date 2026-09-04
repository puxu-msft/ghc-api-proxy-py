"""Does anything at all reach the terminal when the proxy starts?

Runs the real CLI under a pty and dumps the raw bytes. A pty is required rather than a pipe: the footer decides from the stream, so capturing through a pipe would answer a different question than the one being asked.
"""

import json
import os
import pty
import select
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = 41998
# The console script, not `python -c`, because that is what the operator actually types and the two are not guaranteed to behave alike.
command = ["ghc-api-proxy", "start", "--port", str(PORT)]
master, slave = pty.openpty()
environment = {**os.environ, "TERM": "xterm-256color"}
process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, env=environment)
os.close(slave)

chunks: list[bytes] = []


def drain(seconds: float) -> None:
    deadline = seconds
    while deadline > 0:
        ready, _, _ = select.select([master], [], [], 0.5)
        deadline -= 0.5
        if not ready:
            continue
        try:
            data = os.read(master, 65536)
        except OSError:
            return
        if not data:
            return
        chunks.append(data)


drain(6.0)

# An unknown model is refused by routing before any upstream call, so the request-log path runs end to end without spending quota or touching the real service.
body = json.dumps({"model": "no-such-model", "messages": [], "max_tokens": 1}).encode()
request = urllib.request.Request(
    f"http://127.0.0.1:{PORT}/v1/messages", data=body, headers={"content-type": "application/json"}
)
try:
    urllib.request.urlopen(request, timeout=10).read()
except urllib.error.HTTPError as error:
    print(f"request answered {error.code}")
except Exception as error:  # noqa: BLE001 - the probe reports whatever happened
    print(f"request failed: {error!r}")

time.sleep(1.0)
drain(3.0)

process.terminate()
process.wait(timeout=10)
os.close(master)

raw = b"".join(chunks)
print(f"captured {len(raw)} bytes")
print("--- rendered ---")
print(raw.decode(errors="replace"))
