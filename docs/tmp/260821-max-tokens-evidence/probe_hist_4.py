#!/usr/bin/env python3
"""Read-only: dump the tail of every hit operation, root (upstream) frames only."""

from __future__ import annotations

import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

import orjson
import zstandard

H = Path.home() / ".local/share/copilot-api"
DEC = zstandard.ZstdDecompressor()


def all_frames(db: sqlite3.Connection, op: str) -> tuple[list[tuple[int, str, dict[str, Any]]], set[str]]:
    man = orjson.loads(DEC.decompress(db.execute("select manifest_gz from v3_operations where operation_id=?", (op,)).fetchone()[0]))
    hashes = man["objectHashes"]
    events: list[dict[str, Any]] = []
    for (blob,) in db.execute("select payload_gz from v3_timeline_chunks where operation_id=? order by chunk_index", (op,)):
        events.extend(orjson.loads(DEC.decompress(blob)))
    derived = {
        o["handle"]
        for e in events
        if e.get("type") == "transform"
        for o in e.get("value", {}).get("outputs", [])
        if o.get("kind") == "frame"
    }
    out: list[tuple[int, str, dict[str, Any]]] = []
    for e in sorted((e for e in events if e.get("type") == "frame"), key=lambda e: int(e["sequence"])):
        handle = str(e.get("handle", ""))
        if handle in derived:
            continue
        d = hashes.get(handle)
        if d is None:
            continue
        st = db.execute("select canonical_gz from v3_objects where hash=?", (d,)).fetchone()
        if st is None:
            continue
        fr = orjson.loads(DEC.decompress(st[0]))
        raw = fr.get("data")
        if not isinstance(raw, str):
            continue
        try:
            payload = orjson.loads(raw)
        except orjson.JSONDecodeError:
            continue
        out.append((int(e["sequence"]), str(fr.get("event") or payload.get("type", "")), cast(dict[str, Any], payload)))
    return out, derived


def main() -> None:
    hits: list[tuple[str, str]] = []
    for line in Path("/tmp/scan_hits.txt").read_text().splitlines():
        m = re.match(r"HIT (\S+) (\S+) ", line)
        if m:
            hits.append((m.group(1), m.group(2)))
    want = sys.argv[1] if len(sys.argv) > 1 else None
    for dbname, op in hits:
        if want and want not in op:
            continue
        db = sqlite3.connect(f"file:{H/dbname}?immutable=1", uri=True)
        summary = db.execute("select summary_json from v3_operations where operation_id=?", (op,)).fetchone()
        s = orjson.loads(summary[0]) if summary and summary[0] else {}
        frames, _ = all_frames(db, op)
        names = Counter(n for _, n, _ in frames)
        responsesish = any(n.startswith("response.") for _, n, _ in frames)
        print(f"\n##### {dbname} {op} endpoint={s.get('endpoint')} model={s.get('responseModel')} stream={s.get('stream')} success={s.get('responseSuccess')} responses_leg={responsesish}")
        print("   root frame names:", names.most_common())
        for seq, n, pl in frames[-14:]:
            body = orjson.dumps(pl).decode()
            print(f"   [{seq}] {n}: {body[:600]}")
        db.close()


if __name__ == "__main__":
    main()
