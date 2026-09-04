#!/usr/bin/env bash
# Apply one mutation to the snapshot, run a targeted subset, restore.
# Usage: mutate.sh <label> <python-mutator-file> <pytest-args...>
set -u
SNAP=/tmp/rev-tw/snap
PRISTINE=/tmp/rev-tw/pristine
PY=/home/xp/src/ghc-api-proxy-py/.venv/bin/python

label="$1"; shift
mutator="$1"; shift

# restore everything first
rsync -a --delete "$PRISTINE/src/" "$SNAP/src/"

echo "=============================================="
echo "MUTATION: $label"
echo "=============================================="
"$PY" "$mutator" || { echo "MUTATOR FAILED"; exit 2; }

cd "$SNAP"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$SNAP/src" timeout 900 "$PY" -m pytest "$@" -q -p no:randomly 2>&1 | tail -30

# restore
rsync -a --delete "$PRISTINE/src/" "$SNAP/src/"
echo "--- restored; verifying tree matches pristine ---"
diff -r "$PRISTINE/src" "$SNAP/src" >/dev/null && echo "RESTORE OK" || echo "RESTORE FAILED"
