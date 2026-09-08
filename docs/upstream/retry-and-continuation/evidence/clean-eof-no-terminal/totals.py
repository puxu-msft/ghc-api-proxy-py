"""Phase G: the grand total across all four frame-bearing databases.

Same joins as `summarize.py`, one table instead of four.

usage: totals.py   (paths are fixed; edit here if the intermediates move)
"""

from __future__ import annotations

import collections
from pathlib import Path
from typing import Any

import orjson

BASE = Path("/tmp/ceof")
TAGS = ["history-v3-260807", "history-v3-260809", "260811", "history-v3"]
DB_NAME = {
    "history-v3-260807": "history-v3-260807.db",
    "history-v3-260809": "history-v3-260809.db",
    "260811": "history-v3-260811.db",
    "history-v3": "history-v3.db",
}
LEGAL_TERMINAL = {"response.completed", "response.incomplete", "message_stop"}
CLEAN_EOF = "stream truncated: closed without"


def ending(row: dict[str, Any]) -> str:
    settled = row.get("settled") or []
    if not settled:
        return "no-settle-diagnostic"
    last = settled[-1]
    if last.get("success"):
        return "ok"
    error = str(last.get("error") or "")
    if CLEAN_EOF in error:
        return "clean-eof-no-terminal"
    if "client disconnect" in error.lower():
        return "client-disconnect"
    if "NGHTTP2" in error or "Stream closed" in error:
        return "transport-reset"
    if "abort" in error.lower():
        return "aborted"
    return "other-error"


def main() -> None:
    grand_streams = 0
    grand_class = collections.Counter()
    grand_where = collections.Counter()
    per_db: list[tuple[str, int, int, int, int]] = []
    boundary_cases: list[dict[str, Any]] = []
    disagreements = 0

    for tag in TAGS:
        tails = {}
        for line in (BASE / f"{tag}.tails.jsonl").open("rb"):
            row = orjson.loads(line)
            tails[row["oid"]] = row["tail"]
        comp = {}
        for line in (BASE / f"{tag}.cand.jsonl").open("rb"):
            row = orjson.loads(line)
            comp[row["oid"]] = row

        streams = 0
        clean = 0
        at_boundary = 0
        for line in (BASE / f"{tag}.jsonl").open("rb"):
            row = orjson.loads(line)
            if not row.get("n_upstream"):
                continue
            streams += 1
            seen = any(name in LEGAL_TERMINAL for name in tails.get(row["oid"], []))
            klass = ending(row)
            grand_class[(klass, seen)] += 1
            if (klass == "ok" and not seen) or (klass == "clean-eof-no-terminal" and seen):
                disagreements += 1
            if klass != "clean-eof-no-terminal":
                continue
            clean += 1
            c = comp[row["oid"]]
            where = "at-block-boundary" if c["at_block_boundary"] else ("nothing-opened" if c["nothing_opened"] else "mid-block")
            grand_where[(c["leg"], where)] += 1
            if where != "mid-block":
                at_boundary += 1
                boundary_cases.append({"db": DB_NAME[tag], **{k: c[k] for k in ("oid", "leg", "model", "n_upstream", "last_event", "item_status", "usage_seen", "message_delta", "done_sentinel", "counts")}, "where": where})
        grand_streams += streams
        per_db.append((DB_NAME[tag], streams, clean, at_boundary, len(tails)))

    print("=== population ===")
    for name, streams, clean, at_boundary, _ in per_db:
        print(f"  {name:26s} upstream SSE streams={streams:6d}  clean-EOF-no-terminal={clean:4d}  of which not mid-block={at_boundary}")
    print(f"  {'TOTAL':26s} upstream SSE streams={grand_streams:6d}")
    print(f"=== disagreements between the frame scan and copilot-api-js's own verdict: {disagreements} ===")
    print("=== ending class x terminal-event-actually-present (all four databases) ===")
    for (klass, seen), count in sorted(grand_class.items(), key=lambda kv: -kv[1]):
        print(f"  {count:8d}  {klass:<22} terminal_in_frames={seen}")
    print("=== clean EOF without terminal: where did it land? ===")
    total_clean = sum(grand_where.values())
    for key, count in sorted(grand_where.items(), key=lambda kv: str(kv[0])):
        print(f"  {count:5d}  {key}")
    print(f"  {total_clean:5d}  TOTAL")
    print("=== the cases that were NOT mid-block ===")
    for case in boundary_cases:
        print("  " + orjson.dumps(case).decode())


if __name__ == "__main__":
    main()
