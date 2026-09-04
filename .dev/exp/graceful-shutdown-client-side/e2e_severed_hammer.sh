#!/usr/bin/env bash
# The window opens when the server wakes on the signal and closes when it closes the sockets.
# A client cannot aim at it from outside, so this writes continuously across the signal instead.
set -u
ROOT=/home/xp/src/ghc-api-proxy-py
# Falls back to a directory that is created rather than assumed: with CLAUDE_JOB_DIR unset
# the old default was /tmp/tmp, which does not exist, and since these scripts run under
# `set -u` without `set -e` the failed redirect killed the background start silently and
# left the probe spinning 40s before reporting a confident, wrong result.
TMP="${CLAUDE_JOB_DIR:-/tmp/ghc-shutdown-probes}/tmp"
mkdir -p "$TMP"
cd "$ROOT" || exit 1
HITS=0
for ATTEMPT in 1 2 3; do
    PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
    uv run ghc-api-proxy start --port "$PORT" --pidfile "$TMP/ham-$PORT.pid" --no-history >"$TMP/ham-$PORT.log" 2>&1 &
    CHILD=$!
    for _ in $(seq 1 200); do
        curl --silent --max-time 2 "http://127.0.0.1:$PORT/health/liveness" >/dev/null 2>&1 && break
        sleep 0.2
    done
    python3 - "$PORT" "$CHILD" <<'PY'
import os, signal, socket, subprocess, sys, threading, time
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

pool = [pooled() for _ in range(40)]
request = b"POST /v1/messages HTTP/1.1\r\nHost: t\r\nContent-Length: 2\r\n\r\n{}"
stop = threading.Event()

def hammer():
    # Each connection writes once, staggered, so writes keep landing for a few milliseconds either side of the signal.
    for sock in pool:
        if stop.is_set():
            return
        try:
            sock.sendall(request)
        except OSError:
            return
        time.sleep(0.0002)

writer = threading.Thread(target=hammer, daemon=True)
writer.start()
time.sleep(0.002)
os.kill(child, signal.SIGTERM)
writer.join(timeout=3)
stop.set()
for _ in range(75):
    if subprocess.run(["kill", "-0", str(child)], capture_output=True).returncode != 0:
        break
    time.sleep(0.2)
for sock in pool:
    sock.close()
PY
    kill -KILL "$CHILD" 2>/dev/null; wait "$CHILD" 2>/dev/null
    LINE=$(grep -oE 'stopped.*' "$TMP/ham-$PORT.log" | tail -1)
    echo "attempt $ATTEMPT: $LINE"
    case "$LINE" in *severed*) HITS=$((HITS+1)) ;; esac
done
echo "attempts hitting the severed window: $HITS/3"
