#!/usr/bin/env python3
"""Read-only scan of v3_operation_summaries + v3_journal.error for context-limit literals.

Cheapest first pass: summaries are plain TEXT, no decompression needed.
"""

from __future__ import annotations

import datetime
import glob
import os
import re
import sqlite3

NEEDLES = [
    "exceeds the limit",
    "prompt token count",
    "context_length",
    "context length",
    "too many tokens",
    "maximum context",
    "model_max_prompt_tokens",
    "prompt is too long",
    "too long",
]
PAT = re.compile("|".join(re.escape(n) for n in NEEDLES), re.I)


def ts(t: int | None) -> str:
    return datetime.datetime.fromtimestamp(t / 1000).isoformat(sep=" ")[:19] if t else "?"


for path in sorted(glob.glob("/home/xp/.local/share/copilot-api/history-v3*.db")):
    name = os.path.basename(path)
    db = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
    hits = 0
    for op, sj, prev, model, started in db.execute(
        "select operation_id, summary_json, response_preview_text, request_model, started_at from v3_operation_summaries"
    ):
        blob = " ".join(x for x in (sj, prev) if isinstance(x, str))
        if PAT.search(blob):
            hits += 1
            m = PAT.search(blob)
            print(f"SUMHIT {name} {op} {ts(started)} model={model} needle={m.group(0)!r}")
    # journal error column
    jhits = 0
    try:
        for op, rev, phase, err in db.execute(
            "select operation_id, revision, phase, error from v3_journal where error is not null"
        ):
            if isinstance(err, str) and PAT.search(err):
                jhits += 1
                print(f"JRNHIT {name} {op} rev={rev} phase={phase} {err[:400]!r}")
    except sqlite3.Error as exc:  # table may be absent in an older file
        print(f"  journal scan failed for {name}: {exc}")
    print(f"== {name}: summary hits={hits} journal hits={jhits}")
    db.close()
