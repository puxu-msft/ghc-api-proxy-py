"""Phase D: classify every operation's stream ending and count the shape under investigation.

Input: `scan_manifests.py` output plus (optionally) `tail_events.py` output for the same database.

Two independent classifications, deliberately kept apart so they can be compared:

* `frames` — whether a legal terminal event (`response.completed`, `response.incomplete`, `message_stop`) appears among the last upstream frames. First-hand: it reads what upstream sent.
* `verdict` — what copilot-api-js itself concluded, from its `response.settled` diagnostic. Second-hand, and it is the cross-check rather than the source.

usage: classify.py <manifests jsonl> [<tails jsonl>]
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path
from typing import Any

import orjson

LEGAL_TERMINAL = {"response.completed", "response.incomplete", "message_stop"}
CLEAN_EOF_MARKERS = ("stream truncated: closed without",)


def ending_of(row: dict[str, Any]) -> str:
    """copilot-api-js's own word for how this stream ended."""
    settled = row.get("settled") or []
    if not settled:
        if row.get("upstream_errors"):
            return "upstream_error(no settle)"
        return f"no-settle/terminal={row.get('terminal_outcome')}"
    last = settled[-1]
    if last.get("success"):
        return f"ok/{last.get('stop_reason')}"
    error = last.get("error") or ""
    if any(marker in error for marker in CLEAN_EOF_MARKERS):
        return f"CLEAN-EOF-NO-TERMINAL: {error}"
    return f"error: {error[:60]}"


def main(manifests: str, tails: str | None) -> None:
    tail_of: dict[str, list[str]] = {}
    if tails:
        for line in Path(tails).open("rb"):
            row = orjson.loads(line)
            tail_of[row["oid"]] = row["tail"]

    total = 0
    streamed = 0
    cross = collections.Counter()
    candidates: list[tuple[str, str, str, int, str]] = []
    for line in Path(manifests).open("rb"):
        row = orjson.loads(line)
        total += 1
        if not row.get("n_upstream"):
            continue
        streamed += 1
        tail = tail_of.get(row["oid"])
        seen = any(name in LEGAL_TERMINAL for name in tail) if tail is not None else None
        ending = ending_of(row)
        cross[(seen, ending.split(":")[0] if ending.startswith(("CLEAN-EOF", "error")) else ending)] += 1
        if seen is False or ending.startswith("CLEAN-EOF"):
            candidates.append((row["oid"], ending, str(row.get("response_model")), int(row.get("n_upstream") or 0), str(row.get("created_at"))))

    print(f"operations: {total}   with upstream SSE frames: {streamed}")
    print("=== terminal-in-tail  x  copilot-api-js ending ===")
    for key, count in sorted(cross.items(), key=lambda kv: -kv[1]):
        print(f"  {count:8d}  terminal_in_tail={key[0]!s:<5} ending={key[1]}")
    print(f"=== candidates (no terminal in tail, or self-reported clean-EOF truncation): {len(candidates)} ===")
    for oid, ending, model, n_upstream, created in sorted(candidates, key=lambda c: c[4]):
        print(f"  {oid}  created={created}  model={model}  upstream_frames={n_upstream}  {ending}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
