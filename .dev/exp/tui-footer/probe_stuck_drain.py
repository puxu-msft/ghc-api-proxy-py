"""What keeps a drain from finishing when nothing is in flight.

The reported symptom is a set with only one shape that fits: the footer empty, so this process has no registered request — and `cancel_requests` reporting two, so the server has two live request tasks. A task the server knows about and this process does not is a task that has not reached the point where it registers, which is after the request body has been read.

Two ways a client can produce that, both of which a real one does routinely:
  `--idle`       open a connection and send nothing, the way a pool warms up.
  `--truncated`  announce a Content-Length and then not send all of it.
"""

import os
import pty
import re
import select
import signal
import socket
import subprocess
import sys
import threading
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 42360
ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
MODE = "truncated" if "--truncated" in sys.argv else "idle"
HOW_MANY = 2

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

held: list[socket.socket] = []
for _ in range(HOW_MANY):
    sock = socket.create_connection(("127.0.0.1", PORT), timeout=10)
    if MODE == "truncated":
        # A body that never arrives in full. The server is still reading when the signal lands.
        sock.sendall(
            b"POST /v1/messages HTTP/1.1\r\nHost: localhost\r\n"
            b"Content-Type: application/json\r\nContent-Length: 400\r\n\r\n"
            b'{"model":"claude-sonnet-4.5","messages":[]'
        )
    held.append(sock)
print(f"opened {len(held)} connections in {MODE} mode")

time.sleep(1.0)
signalled = time.monotonic()
print("sending one SIGINT")
process.send_signal(signal.SIGINT)

exited = None
for _ in range(120):
    if process.poll() is not None:
        exited = time.monotonic() - signalled
        break
    time.sleep(0.05)

if exited is None:
    print("STILL RUNNING 6s after one SIGINT — reproduced")
    print("escalating with a second SIGINT")
    process.send_signal(signal.SIGINT)
    for _ in range(80):
        if process.poll() is not None:
            exited = time.monotonic() - signalled
            break
        time.sleep(0.05)
    if exited is None:
        process.kill()
        print("needed SIGKILL")
    else:
        print(f"exited {exited:.2f}s after the first signal, only once escalated")
else:
    print(f"exited {exited:.2f}s after one signal — not reproduced")

reading = False
time.sleep(0.3)
for sock in held:
    sock.close()
os.close(master)

print("\n--- lines, with seconds since the signal ---")
for when, chunk in seen:
    for line in ANSI.sub("", chunk.decode(errors="replace")).replace("\r", "\n").splitlines():
        if line.startswith(("[ OK ]", "[FAIL]", "[....]", "[RETRY]", "[<-->]", "[DRIN]")):
            print(f"{when - signalled:+6.2f}s  {line}")
