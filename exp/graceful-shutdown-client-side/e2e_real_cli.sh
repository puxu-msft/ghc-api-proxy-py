#!/usr/bin/env bash
# End-to-end against the real CLI process, in the shape the incident actually had.
#
# The drain window has to be open for the bug to be reachable at all: with nothing in flight the
# whole shutdown finishes in milliseconds and no client can get a request in edgeways. In production
# that window was a model response still streaming. Here it is a request whose body is still on its
# way — same effect, no upstream needed.
#
#   A: POST with a body it has not finished sending  -> the drain waits for it, correctly
#   B: a pooled keep-alive connection that sends a request mid-drain
#   then A is completed, so the only thing that could still hold the shutdown is B
#
# Runs on its own free port and its own pidfile. Signals only the child it started.
set -u

ROOT=/home/xp/src/ghc-api-proxy-py
# Falls back to a directory that is created rather than assumed: with CLAUDE_JOB_DIR unset
# the old default was /tmp/tmp, which does not exist, and since these scripts run under
# `set -u` without `set -e` the failed redirect killed the background start silently and
# left the probe spinning 40s before reporting a confident, wrong result.
TMP="${CLAUDE_JOB_DIR:-/tmp/ghc-shutdown-probes}/tmp"
mkdir -p "$TMP"
PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
PIDFILE="$TMP/e2e-$PORT.pid"

echo "[e2e] starting the real proxy on port $PORT"
cd "$ROOT" || exit 1
uv run ghc-api-proxy start --port "$PORT" --pidfile "$PIDFILE" --no-history >"$TMP/e2e.log" 2>&1 &
CHILD=$!

for _ in $(seq 1 200); do
    if curl --silent --max-time 2 "http://127.0.0.1:$PORT/health/liveness" >/dev/null 2>&1; then
        break
    fi
    sleep 0.2
done

python3 - "$PORT" "$CHILD" <<'PY'
import json, socket, subprocess, sys, time

port, child = int(sys.argv[1]), int(sys.argv[2])


def alive() -> bool:
    return subprocess.run(["kill", "-0", str(child)], capture_output=True).returncode == 0


body = json.dumps(
    {"model": "gpt-5.5", "max_tokens": 16, "messages": [{"role": "user", "content": "hi"}]}
).encode()
head, tail = body[:10], body[10:]

# A: announces the whole body, sends part of it. The handler is now waiting on the rest.
a = socket.create_connection(("127.0.0.1", port), timeout=10)
a.sendall(
    b"POST /v1/messages HTTP/1.1\r\nHost: localhost\r\n"
    b"Content-Type: application/json\r\n"
    b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + head
)
a.settimeout(1.5)
try:
    early = a.recv(4096)
    print(f"[e2e] ABORT: the server answered A without its body: {early[:80]!r}", flush=True)
    sys.exit(2)
except TimeoutError:
    print("[e2e] A is in flight: the server is waiting for the rest of its body", flush=True)

# B: an ordinary pooled connection, idle after one completed request.
b = socket.create_connection(("127.0.0.1", port), timeout=10)
b.sendall(b"GET /health/liveness HTTP/1.1\r\nHost: localhost\r\n\r\n")
print(f"[e2e] B pooled: {b.recv(4096).splitlines()[0]!r}", flush=True)

print("[e2e] one SIGTERM", flush=True)
subprocess.run(["kill", "-TERM", str(child)], check=False)
time.sleep(0.4)

print("[e2e] B sends a request mid-drain, the way a pooled client does", flush=True)
try:
    b.sendall(b"GET /health/liveness HTTP/1.1\r\nHost: localhost\r\n\r\n")
except OSError as closed:
    print(f"[e2e] B was already closed by the server: {closed}", flush=True)

time.sleep(0.4)
if not alive():
    print("[e2e] ABORT: the process exited while A was still in flight — rung 1 cut a live request", flush=True)
    sys.exit(2)

print("[e2e] finishing A's body, so nothing legitimate is left to wait for", flush=True)
a.sendall(tail)

deadline = time.time() + 15
while time.time() < deadline:
    if not alive():
        print(f"[e2e] RESULT: exited {15 - (deadline - time.time()):.1f}s after A completed", flush=True)
        sys.exit(0)
    time.sleep(0.2)
print("[e2e] RESULT: HUNG — 15s after the last live request finished, still running", flush=True)
sys.exit(1)
PY
STATUS=$?

kill -KILL "$CHILD" 2>/dev/null
wait "$CHILD" 2>/dev/null
echo "[e2e] --- last lines of the server's own output ---"
tail -8 "$TMP/e2e.log"
exit $STATUS
