"""Does Ctrl-C say anything, and does it say it at once?

The other probes here watch a request. This one watches the operator's most common action and the one the terminal used to answer with silence: press Ctrl-C, and see whether the process reports what it is doing while it does it.

Timing is the point, not just presence. A line that arrives only after the drain finishes is no better than no line — the whole question the operator has, in the seconds after pressing the key, is whether anything is happening at all.
"""

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
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 42311
ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")

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


pump = threading.Thread(target=reader, daemon=True)
pump.start()
time.sleep(6.0)

# `--busy` is the case the display exists for: a drain that has something to drain, and an operator who presses the key a second time because the first appeared to do nothing.
busy = "--busy" in sys.argv
if busy:
    body = json.dumps(
        {
            "model": "claude-sonnet-4.5",
            "max_tokens": 2048,
            "stream": True,
            "messages": [{"role": "user", "content": "Count from 1 to 300, one number per line."}],
        }
    ).encode()

    def fire() -> None:
        request = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/v1/messages",
            data=body,
            headers={"content-type": "application/json", "anthropic-version": "2023-06-01"},
        )
        try:
            urllib.request.urlopen(request, timeout=60).read()
        except Exception as error:  # noqa: BLE001 - the probe reports whatever happened
            print(f"in-flight request ended: {error!r}")

    threading.Thread(target=fire, daemon=True).start()
    # Short enough that the signal lands while the request is still running. Waiting longer let it finish first, and a drain with nothing to drain exercises none of what this mode is for.
    time.sleep(0.6)

signalled = time.monotonic()
print(f"sending SIGINT to pid {process.pid}")
process.send_signal(signal.SIGINT)

if busy and "--single" not in sys.argv:
    # The second key press, which is what escalates a drain into an interruption.
    time.sleep(1.5)
    print("sending a second SIGINT")
    process.send_signal(signal.SIGINT)

exited = None
for _ in range(200):
    if process.poll() is not None:
        exited = time.monotonic()
        break
    time.sleep(0.05)
if exited is None:
    print("did not exit within 10s; escalating")
    process.send_signal(signal.SIGINT)
    process.wait(timeout=10)
    exited = time.monotonic()

time.sleep(0.5)
reading = False
pump.join(timeout=5)
os.close(master)

print(f"exited {exited - signalled:.2f}s after the signal\n")
print("--- lines, with seconds since the signal ---")
for when, chunk in seen:
    for line in ANSI.sub("", chunk.decode(errors="replace")).replace("\r", "\n").splitlines():
        if line.startswith(("[ OK ]", "[FAIL]", "[....]", "[RETRY]", "[<-->]", "[DRIN]")):
            print(f"{when - signalled:+6.2f}s  {line}")
