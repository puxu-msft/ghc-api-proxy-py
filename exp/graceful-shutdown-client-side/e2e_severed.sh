#!/usr/bin/env bash
set -u
ROOT=/home/xp/src/ghc-api-proxy-py
TMP="${CLAUDE_JOB_DIR:-/tmp}/tmp"
cd "$ROOT" || exit 1

for GAP in -0.05 0.0 0.002 0.05; do
    PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
    uv run ghc-api-proxy start --port "$PORT" --pidfile "$TMP/sev-$PORT.pid" --no-history >"$TMP/sev-$PORT.log" 2>&1 &
    CHILD=$!
    for _ in $(seq 1 200); do
        curl --silent --max-time 2 "http://127.0.0.1:$PORT/health/liveness" >/dev/null 2>&1 && break
        sleep 0.2
    done
    python3 - "$PORT" "$CHILD" "$GAP" <<'PY'
import os, signal, socket, subprocess, sys, time

port, child, gap = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3])

def pooled():
    """One completed keep-alive request, with its response read to the last byte."""
    sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    sock.sendall(b"GET /health/liveness HTTP/1.1\r\nHost: t\r\n\r\n")
    buf = b""
    while b"\r\n\r\n" not in buf:
        buf += sock.recv(4096)
    head, _, body = buf.partition(b"\r\n\r\n")
    length = next(int(l.split(b":")[1]) for l in head.split(b"\r\n") if l.lower().startswith(b"content-length"))
    while len(body) < length:
        body += sock.recv(4096)
    return sock

quiet, loud = pooled(), pooled()
request = b"POST /v1/messages HTTP/1.1\r\nHost: t\r\nContent-Length: 2\r\n\r\n{}"
if gap < 0:
    loud.sendall(request); os.kill(child, signal.SIGTERM)
else:
    os.kill(child, signal.SIGTERM)
    if gap:
        time.sleep(gap)
    try:
        loud.sendall(request)
    except OSError as error:
        print(f"  write failed: {type(error).__name__}", flush=True)
loud.settimeout(3)
try:
    seen = loud.recv(4096)
    print(f"  client saw: {seen[:44]!r}" if seen else "  client saw: clean EOF, no answer", flush=True)
except OSError as error:
    print(f"  client saw: {type(error).__name__}", flush=True)
for _ in range(75):
    if subprocess.run(["kill", "-0", str(child)], capture_output=True).returncode != 0:
        break
    time.sleep(0.2)
quiet.close(); loud.close()
PY
    kill -KILL "$CHILD" 2>/dev/null; wait "$CHILD" 2>/dev/null
    echo "gap=${GAP}: $(grep -oE 'stopped.*' "$TMP/sev-$PORT.log" | tail -1)"
    echo
done
