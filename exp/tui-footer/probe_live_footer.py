"""Watch the live footer while a real request is actually in flight.

The other probes here answer whether the footer *can* render. This one answers the only question that matters to somebody watching a terminal: does a request that is genuinely running show up on the line, with its model and a clock that moves?

It costs one small upstream call, which is the point — a request that finishes instantly leaves the footer with nothing to draw, and that is exactly how the footer came to be shipped attached to a log stream that did not exist.
"""

import json
import os
import pty
import re
import select
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

PORT = 41997
MODEL = sys.argv[1] if len(sys.argv) > 1 else "claude-sonnet-4.5"
FOOTER = re.compile(r"\[<-->\][^\r\n]*")
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

chunks: list[bytes] = []
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
        chunks.append(data)


pump = threading.Thread(target=reader, daemon=True)
pump.start()
time.sleep(6.0)

# Long enough to still be running while the footer redraws, short enough to be a trivial call.
body = json.dumps(
    {
        "model": MODEL,
        "max_tokens": 512,
        "stream": True,
        "messages": [{"role": "user", "content": "Count from 1 to 40, one number per line."}],
    }
).encode()
request = urllib.request.Request(
    f"http://127.0.0.1:{PORT}/v1/messages",
    data=body,
    headers={"content-type": "application/json", "anthropic-version": "2023-06-01"},
)
try:
    with urllib.request.urlopen(request, timeout=120) as response:
        delivered = len(response.read())
    print(f"streamed {delivered} bytes back")
except urllib.error.HTTPError as error:
    print(f"request answered {error.code}: {error.read()[:300]!r}")
except Exception as error:  # noqa: BLE001 - the probe reports whatever happened
    print(f"request failed: {error!r}")

time.sleep(1.0)
reading = False
pump.join(timeout=5)
process.terminate()
process.wait(timeout=10)
os.close(master)

raw = b"".join(chunks).decode(errors="replace")
footers = [match for match in FOOTER.findall(raw) if match.strip() != "[<-->]"]
print(f"\nfooter frames drawn while in flight: {len(footers)}")
for frame in footers:
    print(f"  {frame}")
print("\n--- log lines ---")
# Carriage returns and erase-line sequences have to come off first. A log line printed while the footer is live is preceded by the footer's own `\r\x1b[2K`, so splitting the raw capture and testing `startswith("[ OK ]")` finds nothing and reads as "no request was ever logged" — which is what this probe reported before, on a run whose raw tail plainly contained the line.
plain = ANSI.sub("", raw).replace("\r", "\n")
for line in plain.splitlines():
    if line.startswith(("[ OK ]", "[FAIL]", "[....]", "[RETRY]")):
        print(line)
