"""Phase B: name the last few upstream frames of every operation.

Reads the tail handles produced by `scan_manifests.py`, fetches only those frame objects and reports each one's SSE event name. No payload is parsed beyond the envelope unless the envelope carries no `event`, which keeps a 500 KB `response.completed` from being decoded just to learn its name.

The point is a first-hand answer to "did upstream send a legal terminal event", independent of copilot-api-js's own verdict — that verdict is then used as a cross-check, not as the source.

usage: tail_events.py <db path> <manifests jsonl> <out jsonl>
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

import orjson
import zstandard


def name_of(frame: dict[str, Any]) -> str:
    event = frame.get("event")
    if isinstance(event, str) and event:
        return event
    raw = frame.get("data")
    if not isinstance(raw, str):
        return f"<no-data:{frame.get('type')}>"
    if raw.strip() == "[DONE]":
        return "[DONE]"
    try:
        payload = orjson.loads(raw)
    except orjson.JSONDecodeError:
        return "<unparsable>"
    if isinstance(payload, dict):
        return str(payload.get("type", "<no-type>"))
    return "<not-object>"


def run(db_path: str, manifests: str, out_path: str) -> None:
    con = sqlite3.connect(f"file:{db_path}?immutable=1", uri=True)
    dec = zstandard.ZstdDecompressor()
    out = Path(out_path).open("wb")
    n = 0
    missing = 0
    for line in Path(manifests).open("rb"):
        row = orjson.loads(line)
        handles = row.get("tail_handles") or []
        if not handles:
            continue
        oid = row["oid"]
        hashes = orjson.loads(
            dec.decompress(
                con.execute(
                    "select manifest_gz from v3_operations where operation_id=?", (oid,)
                ).fetchone()[0]
            )
        )["objectHashes"]
        names: list[str] = []
        for handle in handles:
            digest = hashes.get(handle)
            if digest is None:
                names.append("<no-hash>")
                missing += 1
                continue
            stored = con.execute(
                "select canonical_gz from v3_objects where hash=?", (digest,)
            ).fetchone()
            if stored is None:
                names.append("<no-object>")
                missing += 1
                continue
            names.append(name_of(orjson.loads(dec.decompress(stored[0]))))
        out.write(orjson.dumps({"oid": oid, "tail": names}) + b"\n")
        n += 1
        if n % 5000 == 0:
            print(f"  {n} ops ({missing} unresolved handles)", flush=True)
    out.close()
    print(f"done {db_path}: {n} operations, {missing} unresolved handles -> {out_path}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        raise SystemExit(2)
    run(sys.argv[1], sys.argv[2], sys.argv[3])
