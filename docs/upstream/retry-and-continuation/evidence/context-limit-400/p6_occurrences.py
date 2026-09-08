#!/usr/bin/env python3
"""Read-only: every occurrence of the two context-overflow bodies, with operation identity, leg, model, time, and status.

Prints one line per (operation, distinct body) so the spread across models/accounts/dates is visible.
"""

from __future__ import annotations

import datetime
import glob
import json
import os
import sqlite3
from typing import Any

import orjson
import zstandard

DEC = zstandard.ZstdDecompressor()
MARKERS = ("model_max_prompt_tokens_exceeded", "exceeds the context window", "prompt is too long", "prompt token count of", "context_length_exceeded")


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


rows_out: list[tuple[str, str, str, str, str, int, str]] = []
for path in sorted(glob.glob("/home/xp/.local/share/copilot-api/history-v3*.db")):
    name = os.path.basename(path)
    db = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
    for op, model, respmodel, endpoint, started in db.execute(
        "select operation_id, request_model, response_model, endpoint, started_at"
        " from v3_operation_summaries where response_success is null or response_success=0 or state<>'completed'"
    ):
        events: list[dict[str, Any]] = []
        for (blob,) in db.execute(
            "select payload_gz from v3_timeline_chunks where operation_id=? order by chunk_index", (op,)
        ):
            events.extend(orjson.loads(DEC.decompress(blob)))
        found: list[dict[str, Any]] = []
        walk([e for e in events if e.get("type") != "frame"], found)
        seen: set[str] = set()
        for node in found:
            body = str(node["responseText"])
            if not any(m in body for m in MARKERS) or body in seen:
                continue
            seen.add(body)
            rows_out.append((ts(started), name, op, str(model), str(respmodel), int(node["status"]), body))
    db.close()

rows_out.sort()
print(f"{len(rows_out)} occurrences\n")
for when, name, op, model, respmodel, status, body in rows_out:
    print(f"{when} {status} req_model={model} resolved={respmodel} {name} {op}")
    print(f"    {body}")
print()
shapes: dict[str, int] = {}
for *_rest, body in rows_out:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = {"<unparseable>": True}
    err = parsed.get("error", {}) if isinstance(parsed, dict) else {}
    key = json.dumps(
        {
            "top_level_keys": sorted(parsed.keys()) if isinstance(parsed, dict) else None,
            "error_keys": sorted(err.keys()) if isinstance(err, dict) else None,
            "error.code": err.get("code") if isinstance(err, dict) else None,
            "error.type": err.get("type") if isinstance(err, dict) else None,
            "top.type": parsed.get("type") if isinstance(parsed, dict) else None,
        },
        sort_keys=True,
    )
    shapes[key] = shapes.get(key, 0) + 1
print("distinct field shapes:")
for key, count in sorted(shapes.items(), key=lambda kv: -kv[1]):
    print(f"  {count:4d}x {key}")
