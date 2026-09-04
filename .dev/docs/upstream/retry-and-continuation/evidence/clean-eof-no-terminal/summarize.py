"""Phase F: the three numbers, per database.

Joins `scan_manifests.py`, `tail_events.py` and `completeness.py` into the tables the report needs.

The population is one upstream SSE response per operation. An operation with no `upstream-capture` frame never had one (non-streaming request, or torn before headers) and is excluded from the denominator rather than counted as a silent success.

usage: summarize.py <tag> <manifests jsonl> <tails jsonl> <candidates jsonl>
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path
from typing import Any

import orjson

LEGAL_TERMINAL = {"response.completed", "response.incomplete", "message_stop"}
CLEAN_EOF = "stream truncated: closed without"


def ending(row: dict[str, Any]) -> tuple[str, str]:
    settled = row.get("settled") or []
    if not settled:
        return ("no-settle", f"terminal={row.get('terminal_outcome')}")
    last = settled[-1]
    if last.get("success"):
        return ("ok", str(last.get("stop_reason")))
    error = str(last.get("error") or "")
    if CLEAN_EOF in error:
        return ("clean-eof-no-terminal", error)
    if "client disconnect" in error.lower():
        return ("client-disconnect", error)
    if "NGHTTP2" in error or "Stream closed" in error:
        return ("transport-reset", error)
    return ("other-error", error[:80])


def main(tag: str, manifests: str, tails: str, cands: str) -> None:
    tail_of = {}
    for line in Path(tails).open("rb"):
        row = orjson.loads(line)
        tail_of[row["oid"]] = row["tail"]
    comp = {}
    for line in Path(cands).open("rb"):
        row = orjson.loads(line)
        comp[row["oid"]] = row

    streamed = 0
    total = 0
    by_class = collections.Counter()
    disagree: list[str] = []
    boundary = collections.Counter()
    detail: list[dict[str, Any]] = []
    for line in Path(manifests).open("rb"):
        row = orjson.loads(line)
        total += 1
        if not row.get("n_upstream"):
            continue
        streamed += 1
        tail = tail_of.get(row["oid"], [])
        seen = any(name in LEGAL_TERMINAL for name in tail)
        klass, text = ending(row)
        by_class[(klass, seen)] += 1
        if klass == "ok" and not seen:
            disagree.append(f"{row['oid']} ok/{text} but no terminal in tail: {tail}")
        if klass == "clean-eof-no-terminal" and seen:
            disagree.append(f"{row['oid']} self-reported truncation but terminal in tail: {tail}")
        if klass == "clean-eof-no-terminal":
            c = comp.get(row["oid"])
            if c is None:
                boundary["<not analysed>"] += 1
                continue
            where = "at-block-boundary" if c["at_block_boundary"] else ("nothing-opened" if c["nothing_opened"] else "mid-block")
            boundary[(c["leg"], where)] += 1
            detail.append(
                {
                    "oid": row["oid"],
                    "leg": c["leg"],
                    "model": c["model"],
                    "n_upstream": c["n_upstream"],
                    "where": where,
                    "unclosed": c["unclosed_item_types"] + c["unclosed_block_types"],
                    "last_event": c["last_event"],
                    "usage_seen": c["usage_seen"] is not None,
                    "message_delta": c["message_delta"] is not None,
                    "done_sentinel": c["done_sentinel"],
                    "created_at": c["created_at"],
                }
            )

    print(f"### {tag}: {total} operations, {streamed} with an upstream SSE stream")
    print("--- ending class x terminal-event-actually-present ---")
    for (klass, seen), count in sorted(by_class.items(), key=lambda kv: -kv[1]):
        print(f"  {count:8d}  {klass:<24} terminal_in_frames={seen}")
    print(f"--- disagreements between the two classifications: {len(disagree)} ---")
    for line in disagree[:20]:
        print("  ", line)
    print("--- clean EOF without terminal: where did it land? ---")
    for key, count in sorted(boundary.items(), key=lambda kv: str(kv[0])):
        print(f"  {count:5d}  {key}")
    print("--- per case ---")
    for row in sorted(detail, key=lambda r: r["created_at"] or 0):
        print("  " + orjson.dumps(row).decode())


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(__doc__)
        raise SystemExit(2)
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
