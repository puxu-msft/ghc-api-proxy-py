#!/usr/bin/env python3
"""Read-only: dump everything recorded for one operation id — summary, manifest, timeline events, and every referenced object."""

from __future__ import annotations

import datetime
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import orjson
import zstandard

H = Path.home() / ".local/share/copilot-api"
DEC = zstandard.ZstdDecompressor()


def ts(t: int | None) -> str:
    return datetime.datetime.fromtimestamp(t / 1000).isoformat(sep=" ") if t else "?"


def main(dbname: str, op: str) -> None:
    db = sqlite3.connect(f"file:{H / dbname}?immutable=1", uri=True)
    row = db.execute(
        "select summary_json, response_preview_text, preview_text, request_model, response_model,"
        " response_success, endpoint, state, started_at, ended_at, input_tokens, output_tokens"
        " from v3_operation_summaries where operation_id=?",
        (op,),
    ).fetchone()
    print("=" * 100)
    print(f"OPERATION {op}  db={dbname}")
    if row:
        (sj, rprev, prev, rmodel, respmodel, ok, endpoint, state, started, ended, itok, otok) = row
        print(f"  endpoint={endpoint} state={state} success={ok} req_model={rmodel} resp_model={respmodel}")
        print(f"  started={ts(started)} ended={ts(ended)} in={itok} out={otok}")
        print(f"  preview_text={prev!r}")
        print(f"  response_preview_text={rprev!r}")
        print("  summary_json:")
        print(json.dumps(json.loads(sj), indent=2, ensure_ascii=False) if sj else "    None")

    orow = db.execute("select manifest_gz, kind, summary_json, terminal_sequence from v3_operations where operation_id=?", (op,)).fetchone()
    if orow is None:
        print("  no v3_operations row")
        return
    man = orjson.loads(DEC.decompress(orow[0]))
    print(f"  manifest keys: {sorted(man.keys())}")
    hashes: dict[str, str] = man.get("objectHashes", {})
    print(f"  objectHashes: {len(hashes)}")

    events: list[dict[str, Any]] = []
    for (blob,) in db.execute("select payload_gz from v3_timeline_chunks where operation_id=? order by chunk_index", (op,)):
        events.extend(orjson.loads(DEC.decompress(blob)))
    print(f"  timeline events: {len(events)}")
    from collections import Counter

    print("  event types:", Counter(str(e.get("type")) for e in events))

    def obj(handle: str) -> Any:
        d = hashes.get(handle)
        if d is None:
            return None
        st = db.execute("select kind, canonical_gz from v3_objects where hash=?", (d,)).fetchone()
        if st is None:
            return None
        return (st[0], orjson.loads(DEC.decompress(st[1])))

    for e in events:
        t = str(e.get("type"))
        if t == "frame":
            continue
        print(f"\n  --- seq={e.get('sequence')} type={t} handle={e.get('handle')}")
        print("      " + json.dumps(e, ensure_ascii=False)[:4000])
        h = e.get("handle")
        if isinstance(h, str):
            o = obj(h)
            if o is not None:
                kind, payload = o
                print(f"      OBJECT kind={kind}:")
                print("      " + json.dumps(payload, ensure_ascii=False, indent=2)[:20000].replace("\n", "\n      "))

    frames = [e for e in events if e.get("type") == "frame"]
    print(f"\n  frames: {len(frames)}")
    for e in frames[:40]:
        o = obj(str(e.get("handle", "")))
        if o is None:
            print(f"    seq={e.get('sequence')} handle={e.get('handle')} <no object>")
            continue
        kind, fr = o
        print(f"    seq={e.get('sequence')} event={fr.get('event')!r} data={str(fr.get('data'))[:2000]!r}")
    if len(frames) > 40:
        print(f"    ... {len(frames) - 40} more frames")
    db.close()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
