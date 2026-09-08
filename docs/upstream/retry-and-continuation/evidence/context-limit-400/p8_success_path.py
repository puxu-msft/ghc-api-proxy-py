#!/usr/bin/env python3
"""Read-only: close the success-path blind spot.

p3-p6 only looked at operations the JS service recorded as non-success, so an operation that took a 400 on
its first candidate and then succeeded on a fallback would have been invisible. This scans the *first*
timeline chunk of **every** operation — where a primary candidate's early failure is recorded — and reports
any 4xx whose body mentions a context/prompt limit, plus a count of every 4xx seen, so the zero is a checked zero.
"""

from __future__ import annotations

import datetime
import glob
import os
import sqlite3
from collections import Counter
from typing import Any

import orjson
import zstandard

DEC = zstandard.ZstdDecompressor()
MARKERS = ("model_max_prompt_tokens", "exceeds the context window", "prompt is too long", "prompt token count of", "context_length_exceeded", "maximum context", "too many tokens")


def ts(t: int | None) -> str:
    return datetime.datetime.fromtimestamp(t / 1000).isoformat(sep=" ")[:19] if t else "?"


def walk(node: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(node, dict):
        if isinstance(node.get("responseText"), str) and isinstance(node.get("status"), int):
            out.append(node)
        for v in node.values():
            walk(v, out)
    elif isinstance(node, list):
        for v in node:
            walk(v, out)


grand: Counter[str] = Counter()
for path in sorted(glob.glob("/home/xp/.local/share/copilot-api/history-v3*.db")):
    name = os.path.basename(path)
    db = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
    success = {
        op: (model, respmodel, started)
        for op, model, respmodel, started in db.execute(
            "select operation_id, request_model, response_model, started_at from v3_operation_summaries"
            " where response_success=1 and state='completed'"
        )
    }
    seen_ops = 0
    per_db: Counter[str] = Counter()
    for op, blob in db.execute("select operation_id, payload_gz from v3_timeline_chunks where chunk_index=0"):
        if op not in success:
            continue
        seen_ops += 1
        events = orjson.loads(DEC.decompress(blob))
        found: list[dict[str, Any]] = []
        walk([e for e in events if e.get("type") != "frame"], found)
        for node in found:
            status = int(node["status"])
            if not 400 <= status < 500:
                continue
            body = str(node["responseText"])
            per_db[str(status)] += 1
            grand[str(status)] += 1
            if any(m in body for m in MARKERS):
                model, respmodel, started = success[op]
                print(f"LIMIT-ON-SUCCESS {name} {op} {ts(started)} {status} req={model} resolved={respmodel}")
                print(f"    {body[:800]}", flush=True)
    print(f"== {name}: successful ops with a chunk-0 scanned = {seen_ops}; 4xx seen in them = {dict(per_db)}", flush=True)
    db.close()
print(f"TOTAL 4xx inside successful operations: {dict(grand)}")
