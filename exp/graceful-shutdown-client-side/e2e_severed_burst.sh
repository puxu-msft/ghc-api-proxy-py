#!/usr/bin/env bash
# The severed window is about one event-loop iteration wide, so one client rarely lands in it.
# Twenty pooled connections all writing across the signal makes it very likely at least one does.
set -u
ROOT=/home/xp/src/ghc-api-proxy-py
TMP="${CLAUDE_JOB_DIR:-/tmp}/tmp"
cd "$ROOT" || exit 1
PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
uv run ghc-api-proxy start --port "$PORT" --pidfile "$TMP/burst-$PORT.pid" --no-history >"$TMP/burst.log" 2>&1 &
CHILD=$!
for _ in $(seq 1 200); do
    curl --silent --max-time 2 "http://127.0.0.1:$PORT/health/liveness" >/dev/null 2>&1 && break
    sleep 0.2
done
python3 - "$PORT" "$CHILD" <<'PY'
import os, signal, socket, subprocess, sys, time
port, child = int(sys.argv[1]), int(sys.argv[2])

def pooled():
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

pool = [pooled() for _ in range(20)]
print(f"[burst] {len(pool)} pooled connections idle", flush=True)
request = b"POST /v1/messages HTTP/1.1\r\nHost: t\r\nContent-Length: 2\r\n\r\n{}"
os.kill(child, signal.SIGTERM)
reset = failed = 0
for sock in pool:
    try:
        sock.sendall(request)
    except OSError:
        failed += 1
for sock in pool:
    sock.settimeout(2)
    try:
        if not sock.recv(4096):
            pass
    except ConnectionResetError:
        reset += 1
    except OSError:
        pass
print(f"[burst] clients seeing a reset: {reset}, writes that failed outright: {failed}", flush=True)
for _ in range(75):
    if subprocess.run(["kill", "-0", str(child)], capture_output=True).returncode != 0:
        break
    time.sleep(0.2)
for sock in pool:
    sock.close()
PY
kill -KILL "$CHILD" 2>/dev/null; wait "$CHILD" 2>/dev/null
echo "--- closing line ---"
grep -oE 'stopped.*' "$TMP/burst.log" | tail -1
grep -cE '\[FAIL\]' "$TMP/burst.log" | sed 's/^/FAIL lines: /'
