#!/usr/bin/env python3
"""Read-only: inventory of failed / non-success operations, grouped by the error text recorded on the terminal event.

The summary scan only sees `previewText` (a truncated slice of the *request*), so it cannot find an upstream error body.
This walks every operation's terminal timeline event, which is where the JS service records the failure it settled on.
"""

from __future__ import annotations

import datetime
import glob
import json
import os
import sqlite3
from collections import Counter
from typing import Any

import orjson
import zstandard

DEC = zstandard.ZstdDecompressor()


def ts(t: int | None) -> str:
    return datetime.datetime.fromtimestamp(t / 1000).isoformat(sep=" ")[:19] if t else "?"


for path in sorted(glob.glob("/home/xp/.local/share/copilot-api/history-v3*.db")):
    name = os.path.basename(path)
    db = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
    rows = db.execute(
        "select operation_id, state, response_success, request_model, started_at, endpoint"
        " from v3_operation_summaries where response_success is null or response_success=0 or state<>'completed'"
    ).fetchall()
    print(f"== {name}: {len(rows)} non-success operations")
    outcomes: Counter[str] = Counter()
    for op, state, ok, model, started, endpoint in rows:
        chunks = db.execute(
            "select payload_gz from v3_timeline_chunks where operation_id=? order by chunk_index desc limit 1", (op,)
        ).fetchall()
        term: dict[str, Any] | None = None
        for (blob,) in chunks:
            for e in orjson.loads(DEC.decompress(blob)):
                if e.get("type") == "terminal":
                    term = e
        val = (term or {}).get("value", {})
        err = val.get("error") or val.get("failure") or {}
        key = json.dumps(err, ensure_ascii=False, sort_keys=True)[:300] if err else f"outcome={val.get('outcome')}"
        outcomes[key] += 1
    for key, count in outcomes.most_common(60):
        print(f"   {count:5d}  {key}")
    db.close()
