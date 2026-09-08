#!/usr/bin/env python3
"""Read-only scan: find operations whose tail frames show a max_output_tokens / max_tokens stop.

Only the last K frame objects of each operation are decompressed, which is what makes a full-corpus
scan affordable. The marker is textual and deliberately broad; matches are re-checked by hand.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

import orjson
import zstandard

H = Path.home() / ".local/share/copilot-api"
DEC = zstandard.ZstdDecompressor()
TAIL = 16

MARKERS = (rb'incomplete_details\":{', rb'stop_reason\":\"max_tokens')

DBS = ["history-v3-260807.db", "history-v3-260809.db", "history-v3-260811.db", "history-v3.db"]


def scan(path: Path, limit: int | None) -> None:
    db = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
    q = "select operation_id, manifest_gz from v3_operations order by created_at desc"
    if limit:
        q += f" limit {limit}"
    n = 0
    hits = 0
    t0 = time.time()
    for op, man_gz in db.execute(q):
        n += 1
        try:
            man = orjson.loads(DEC.decompress(man_gz))
        except Exception:
            continue
        hashes = man.get("objectHashes") or {}
        frame_handles = sorted(
            (h for h in hashes if h.startswith("frame:")),
            key=lambda h: int(h.split(":", 1)[1]),
        )
        for h in frame_handles[-TAIL:]:
            row = db.execute("select canonical_gz from v3_objects where hash=?", (hashes[h],)).fetchone()
            if row is None:
                continue
            raw = DEC.decompress(row[0])
            if any(m in raw for m in MARKERS):
                hits += 1
                print(f"HIT {path.name} {op} {h} :: {raw[:400]!r}")
                break
    print(f"# {path.name}: scanned {n} ops, {hits} hits, {time.time()-t0:.1f}s", file=sys.stderr)
    db.close()


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    only = sys.argv[2] if len(sys.argv) > 2 else None
    for name in DBS:
        if only and only != name:
            continue
        scan(H / name, limit)
