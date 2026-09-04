#!/usr/bin/env python3
"""Read-only: for every hit with a Responses leg, tabulate what arrived around the truncation."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, cast

import orjson
import zstandard

H = Path.home() / ".local/share/copilot-api"
DEC = zstandard.ZstdDecompressor()


def frames(db: sqlite3.Connection, op: str) -> list[tuple[int, str, dict[str, Any]]]:
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
    return out


hits: list[tuple[str, str]] = []
for line in Path("/tmp/scan_hits.txt").read_text().splitlines():
    m = re.match(r"HIT (\S+) (\S+) ", line)
    if m:
        hits.append((m.group(1), m.group(2)))

for dbname, op in hits:
    db = sqlite3.connect(f"file:{H/dbname}?immutable=1", uri=True)
    fs = frames(db, op)
    if not any(n == "response.incomplete" for _, n, _ in fs):
        db.close()
        continue
    print(f"\n===== {op} ({dbname})")
    added: list[tuple[int, str]] = []
    done: list[tuple[int, str, str]] = []
    for _, n, pl in fs:
        if n == "response.output_item.added":
            item = pl.get("item") or {}
            added.append((pl.get("output_index", -1), str(item.get("type"))))
        elif n == "response.output_item.done":
            item = pl.get("item") or {}
            done.append((pl.get("output_index", -1), str(item.get("type")), str(item.get("status"))))
    print(f"  added: {added}")
    print(f"  done : {done}")
    # last 8 root event names in order
    print("  tail names:", [n for _, n, _ in fs[-8:]])
    inc = next(pl for _, n, pl in fs if n == "response.incomplete")
    resp = inc.get("response") or {}
    print(f"  incomplete_details = {resp.get('incomplete_details')}  status={resp.get('status')}")
    outs = resp.get("output") or []
    print(f"  response.output has {len(outs)} items:")
    for it in outs:
        it = cast(dict[str, Any], it)
        t = it.get("type")
        status = it.get("status")
        if t == "message":
            texts = [c.get("text", "") for c in it.get("content", []) if isinstance(c, dict)]
            print(f"    - message status={status} content_parts={len(it.get('content', []))} text_len={sum(len(x) for x in texts)} tail={texts[-1][-60:]!r}" if texts else f"    - message status={status} content=[]")
        elif t == "function_call":
            args = str(it.get("arguments", ""))
            try:
                json.loads(args)
                ok = "valid-json"
            except Exception:
                ok = "TRUNCATED-json"
            print(f"    - function_call status={status} name={it.get('name')} args_len={len(args)} {ok} tail={args[-60:]!r}")
        elif t == "reasoning":
            summ = it.get("summary") or []
            enc = it.get("encrypted_content")
            print(f"    - reasoning status={status} summary_parts={len(summ)} enc_len={len(enc) if isinstance(enc, str) else None} content={len(it.get('content') or [])}")
        else:
            print(f"    - {t} status={status} keys={sorted(it.keys())}")
    # compare last output_item.done payload against the same item in response.output
    last_done = next((pl for _, n, pl in reversed(fs) if n == "response.output_item.done"), None)
    if last_done is not None:
        item = cast(dict[str, Any], last_done.get("item") or {})
        if item.get("type") == "function_call":
            a = str(item.get("arguments", ""))
            print(f"  last done item: function_call args_len={len(a)} status={item.get('status')}")
        elif item.get("type") == "message":
            texts = [c.get("text", "") for c in item.get("content", []) if isinstance(c, dict)]
            print(f"  last done item: message text_len={sum(len(x) for x in texts)} status={item.get('status')}")
        else:
            print(f"  last done item: {item.get('type')} status={item.get('status')}")
    db.close()
