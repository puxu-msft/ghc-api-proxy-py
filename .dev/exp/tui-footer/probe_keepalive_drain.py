"""Does a drain finish when the client keeps its connection open?

Every earlier probe here used `urllib`, which closes the socket as soon as it has read the body. Real clients do not: they hold a keep-alive pool open between requests, which is the whole point of one. This probe holds the connection the way a real client does, sends one request, and then asks the process to stop exactly once.

If the drain waits on connections rather than on requests, the request finishes, the footer empties, and the process sits in `[DRIN]` forever — which is indistinguishable, from the terminal, from a hang.
"""

import http.client
import json
import os
import pty
import re
import select
import signal
import subprocess
import sys
import threading
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 42340
ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
CLOSE_AFTER = "--close" in sys.argv
# Streaming is the shape that involves the delivery generator chain, and a generator that is never closed leaves its request task alive — which a drain waits on.
STREAM = "--stream" in sys.argv
# A client that stops reading part-way, which is what happens when a user cancels.
ABANDON = "--abandon" in sys.argv

master, slave = pty.openpty()
process = subprocess.Popen(
    ["ghc-api-proxy", "start", "--port", str(PORT)],
    stdin=slave,
    stdout=slave,
    stderr=slave,
    env={**os.environ, "TERM": "xterm-256color"},
)
os.close(slave)

seen: list[tuple[float, bytes]] = []
reading = True


def reader() -> None:
    while reading:
        ready, _, _ = select.select([master], [], [], 0.5)
        if not ready:
            continue
        try:
            data = os.read(master, 65536)
        except OSError:
            return
        if not data:
            return
        seen.append((time.monotonic(), data))


threading.Thread(target=reader, daemon=True).start()
time.sleep(6.0)

# Held open across the shutdown, which is what a pooled client does between requests.
connection = http.client.HTTPConnection("127.0.0.1", PORT, timeout=60)
connection.request(
    "POST",
    "/v1/messages",
    body=json.dumps(
        {
            "model": "claude-sonnet-4.5",
            "max_tokens": 1024 if STREAM else 256,
            "stream": STREAM,
            "messages": [{"role": "user", "content": "Count from 1 to 120, one number per line." if STREAM else "Say hi."}],
        }
    ),
    headers={"content-type": "application/json", "anthropic-version": "2023-06-01"},
)
answer = connection.getresponse()
if ABANDON:
    # Read one chunk and walk away, leaving the response half-consumed.
    print(f"request answered {answer.status}, abandoned after {len(answer.read(64))} bytes")
else:
    print(f"request answered {answer.status}, {len(answer.read())} bytes")
if CLOSE_AFTER:
    connection.close()
    print("connection closed by the client")
else:
    print("connection left open, as a pooled client would")

time.sleep(0.5)
signalled = time.monotonic()
print("sending one SIGINT")
process.send_signal(signal.SIGINT)

exited = None
for _ in range(160):
    if process.poll() is not None:
        exited = time.monotonic() - signalled
        break
    time.sleep(0.05)

if exited is None:
    print("STILL RUNNING 8s after the signal — the drain did not finish")
    process.kill()
    process.wait(timeout=10)
else:
    print(f"exited {exited:.2f}s after the signal")

reading = False
time.sleep(0.3)
os.close(master)
connection.close()

print("\n--- lines, with seconds since the signal ---")
for when, chunk in seen:
    for line in ANSI.sub("", chunk.decode(errors="replace")).replace("\r", "\n").splitlines():
        if line.startswith(("[ OK ]", "[FAIL]", "[....]", "[RETRY]", "[<-->]", "[DRIN]")):
            print(f"{when - signalled:+6.2f}s  {line}")
