"""Phase E: for a named set of operations, judge block completeness at the moment upstream stopped.

Answers the question the refinement turns on: when a stream ends with no terminal event, is every block closed, or is one still open?

Per operation it reports the leg, the event histogram, which items/blocks opened without closing, and the side clues that might still say "it had finished" — an Anthropic `message_delta` (which carries `stop_reason` and usage ahead of `message_stop`), a `[DONE]` sentinel, or a usage object anywhere in the stream.

usage: completeness.py <db path> <oid file>   (one operation id per line, `#` comments allowed)
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

import orjson
import zstandard

LEGAL_TERMINAL = {"response.completed", "response.incomplete", "message_stop"}


def analyse(con: sqlite3.Connection, dec: zstandard.ZstdDecompressor, oid: str) -> dict[str, Any] | None:
    row = con.execute(
        "select manifest_gz, summary_json from v3_operations where operation_id=?", (oid,)
    ).fetchone()
    if row is None:
        return None
    manifest = orjson.loads(dec.decompress(row[0]))
    rec = manifest["record"]
    hashes = manifest["objectHashes"]
    summary = orjson.loads(row[1]) if row[1] else {}

    handles = [
        (int(f.get("sequence", 0)), str(f.get("handle")))
        for f in rec.get("arena", {}).get("frames", []) or []
        if (f.get("origin") or {}).get("stage") == "upstream-capture"
    ]
    handles.sort()

    counts: dict[str, int] = {}
    opened: dict[Any, str] = {}
    closed: dict[Any, str] = {}
    item_status: dict[Any, Any] = {}
    ab_open: dict[Any, str] = {}
    ab_closed: set[Any] = set()
    message_delta: dict[str, Any] | None = None
    usage_seen: Any = None
    done_sentinel = False
    last_name = ""
    order: list[str] = []

    for _seq, handle in handles:
        digest = hashes.get(handle)
        stored = con.execute("select canonical_gz from v3_objects where hash=?", (digest,)).fetchone() if digest else None
        if stored is None:
            counts["<object missing>"] = counts.get("<object missing>", 0) + 1
            continue
        frame = orjson.loads(dec.decompress(stored[0]))
        raw = frame.get("data")
        payload: Any = None
        if isinstance(raw, str):
            if raw.strip() == "[DONE]":
                done_sentinel = True
                counts["[DONE]"] = counts.get("[DONE]", 0) + 1
                last_name = "[DONE]"
                order.append("[DONE]")
                continue
            try:
                payload = orjson.loads(raw)
            except orjson.JSONDecodeError:
                payload = None
        name = str(frame.get("event") or (payload.get("type") if isinstance(payload, dict) else "<unparsable>"))
        counts[name] = counts.get(name, 0) + 1
        last_name = name
        order.append(name)
        if not isinstance(payload, dict):
            continue
        if name == "response.output_item.added":
            opened[payload.get("output_index")] = str((payload.get("item") or {}).get("type"))
        elif name == "response.output_item.done":
            item = payload.get("item") or {}
            closed[payload.get("output_index")] = str(item.get("type"))
            item_status[payload.get("output_index")] = item.get("status")
        elif name == "content_block_start":
            ab_open[payload.get("index")] = str((payload.get("content_block") or {}).get("type"))
        elif name == "content_block_stop":
            ab_closed.add(payload.get("index"))
        elif name == "message_delta":
            message_delta = {"delta": payload.get("delta"), "usage": payload.get("usage")}
        if payload.get("usage") is not None:
            usage_seen = payload.get("usage")
        response = payload.get("response")
        if isinstance(response, dict) and response.get("usage") is not None:
            usage_seen = response.get("usage")

    leg = "responses" if any(k.startswith("response.") for k in counts) else ("anthropic" if counts else "empty")
    unclosed_items = sorted(str(k) for k in set(opened) - set(closed))
    unclosed_blocks = sorted(str(k) for k in set(ab_open) - ab_closed)
    return {
        "oid": oid,
        "leg": leg,
        "model": summary.get("responseModel"),
        "endpoint": summary.get("endpoint"),
        "created_at": summary.get("startedAt"),
        "n_upstream": len(handles),
        "counts": dict(sorted(counts.items())),
        "opened": len(opened) or len(ab_open),
        "closed": len(closed) or len(ab_closed),
        "unclosed_items": unclosed_items,
        "unclosed_item_types": [opened[k] for k in set(opened) - set(closed)],
        "unclosed_blocks": unclosed_blocks,
        "unclosed_block_types": [ab_open[k] for k in set(ab_open) - ab_closed],
        "item_status": {str(k): v for k, v in item_status.items()},
        "at_block_boundary": not unclosed_items and not unclosed_blocks and bool(opened or ab_open),
        "nothing_opened": not (opened or ab_open),
        "last_event": last_name,
        "tail5": order[-5:],
        "message_delta": message_delta,
        "usage_seen": usage_seen,
        "done_sentinel": done_sentinel,
        "legal_terminal": sorted(k for k in counts if k in LEGAL_TERMINAL),
    }


def main(db_path: str, oid_file: str) -> None:
    con = sqlite3.connect(f"file:{db_path}?immutable=1", uri=True)
    dec = zstandard.ZstdDecompressor()
    for raw in Path(oid_file).read_text().splitlines():
        oid = raw.split("#")[0].strip()
        if not oid:
            continue
        result = analyse(con, dec, oid)
        if result is None:
            print(orjson.dumps({"oid": oid, "missing": True}).decode())
            continue
        print(orjson.dumps(result).decode())


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    main(sys.argv[1], sys.argv[2])
