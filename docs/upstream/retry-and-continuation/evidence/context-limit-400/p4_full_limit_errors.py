#!/usr/bin/env python3
"""Read-only: full, untruncated dump of every terminal-event error that mentions a prompt/context limit.

Finds them by walking terminal events of non-success operations (same population as p3) and printing the
whole error object verbatim, plus the operation's identity and every dispatch/candidate event around it.
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
NEEDLE = ("prompt is too long", "prompt token count", "exceeds the limit", "context_length", "max_prompt_tokens", "context length", "too many tokens", "maximum context")


def ts(t: int | None) -> str:
    return datetime.datetime.fromtimestamp(t / 1000).isoformat(sep=" ") if t else "?"


def hit(text: str) -> bool:
    low = text.lower()
    return any(n in low for n in NEEDLE)


for path in sorted(glob.glob("/home/xp/.local/share/copilot-api/history-v3*.db")):
    name = os.path.basename(path)
    db = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
    rows = db.execute(
        "select operation_id, state, response_success, request_model, response_model, started_at, endpoint"
        " from v3_operation_summaries where response_success is null or response_success=0 or state<>'completed'"
    ).fetchall()
    for op, state, ok, model, respmodel, started, endpoint in rows:
        events: list[dict[str, Any]] = []
        for (blob,) in db.execute(
            "select payload_gz from v3_timeline_chunks where operation_id=? order by chunk_index", (op,)
        ):
            events.extend(orjson.loads(DEC.decompress(blob)))
        raw = json.dumps([e for e in events if e.get("type") != "frame"], ensure_ascii=False)
        if not hit(raw):
            continue
        print("=" * 110)
        print(f"DB {name}  OP {op}")
        print(f"  endpoint={endpoint} state={state} success={ok} req_model={model} resp_model={respmodel} started={ts(started)}")
        for e in events:
            if e.get("type") == "frame":
                continue
            blob = json.dumps(e, ensure_ascii=False)
            if e.get("type") in {"terminal", "dispatch-settled", "candidate-settled", "dispatch", "candidate", "routing", "attempt"} or hit(blob):
                print(f"\n  [seq={e.get('sequence')} {e.get('type')} @{ts(e.get('occurredAt'))}]")
                print(json.dumps(e, ensure_ascii=False, indent=2))
    db.close()
