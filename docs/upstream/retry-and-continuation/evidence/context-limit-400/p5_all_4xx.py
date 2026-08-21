#!/usr/bin/env python3
"""Read-only: every upstream 4xx recorded anywhere in a non-success operation's timeline, grouped by body shape.

Answers "how do I tell this 400 from other 400s" — it needs the *other* 400s, not only the limit one.
Also records which upstream leg produced it (endpoint + resolved model) so the two legs can be compared.
"""

from __future__ import annotations

import datetime
import glob
import json
import os
import re
import sqlite3
from collections import Counter
from typing import Any

import orjson
import zstandard

DEC = zstandard.ZstdDecompressor()
NUM = re.compile(r"\d{3,}")

shapes: Counter[str] = Counter()
examples: dict[str, tuple[str, str, str, str, str]] = {}


def walk(node: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(node, dict):
        status = node.get("status")
        if isinstance(status, int) and 400 <= status < 500 and ("responseText" in node or "message" in node):
            out.append(node)
        for v in node.values():
            walk(v, out)
    elif isinstance(node, list):
        for v in node:
            walk(v, out)


for path in sorted(glob.glob("/home/xp/.local/share/copilot-api/history-v3*.db")):
    name = os.path.basename(path)
    db = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
    rows = db.execute(
        "select operation_id, request_model, response_model, endpoint, started_at"
        " from v3_operation_summaries where response_success is null or response_success=0 or state<>'completed'"
    ).fetchall()
    for op, model, respmodel, endpoint, started in rows:
        events: list[dict[str, Any]] = []
        for (blob,) in db.execute(
            "select payload_gz from v3_timeline_chunks where operation_id=? order by chunk_index", (op,)
        ):
            events.extend(orjson.loads(DEC.decompress(blob)))
        found: list[dict[str, Any]] = []
        walk([e for e in events if e.get("type") != "frame"], found)
        seen: set[str] = set()
        for node in found:
            body = node.get("responseText")
            if not isinstance(body, str):
                continue
            key = f"{node.get('status')} :: {NUM.sub('N', body)[:400]}"
            if key in seen:
                continue
            seen.add(key)
            shapes[key] += 1
            examples.setdefault(key, (name, op, str(respmodel), str(endpoint), body))
    db.close()

when = datetime.datetime.now().isoformat(timespec="seconds")
print(f"# upstream 4xx bodies seen in non-success operations (scan at {when})\n")
for key, count in shapes.most_common():
    name, op, respmodel, endpoint, body = examples[key]
    print(f"--- {count:5d}x  {key.split(' :: ')[0]}  first: {name} {op} endpoint={endpoint} resolved_model={respmodel}")
    print(f"      {body[:1200]}")
    print()
print(json.dumps({"distinct_shapes": len(shapes), "total": sum(shapes.values())}))
