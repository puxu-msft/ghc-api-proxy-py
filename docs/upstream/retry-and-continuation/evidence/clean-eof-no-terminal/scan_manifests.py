"""Phase A: manifest-only scan of a copilot-api history database.

One row per operation, no frame-object decompression. Everything here comes from `v3_operations.manifest_gz`'s `record`, which carries the arena (每帧的 handle 与 origin), the transform graph, the dispatch diagnostics and the terminal verdict.

Key predicate: an *upstream* frame is `origin.stage == "upstream-capture"`. That is the storage layer's own label, and it is strictly better than the "root of the transform graph" heuristic `from_history.py` uses, which is vacuously true on early operations that recorded no transforms at all.

Read-only: every database is opened `file:...?immutable=1`.

usage: scan_manifests.py <db path> <out jsonl>
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

import orjson
import zstandard

TAIL = 12


def scan(db_path: str, out_path: str) -> None:
    con = sqlite3.connect(f"file:{db_path}?immutable=1", uri=True)
    dec = zstandard.ZstdDecompressor()
    out = Path(out_path).open("wb")
    n = 0
    for oid, created_at, summary_json, manifest_gz in con.execute(
        "select operation_id, created_at, summary_json, manifest_gz from v3_operations"
    ):
        try:
            rec = orjson.loads(dec.decompress(manifest_gz))["record"]
        except Exception as exc:  # noqa: BLE001 - a poisoned row must be visible, not silent
            out.write(orjson.dumps({"oid": oid, "manifest_error": repr(exc)}) + b"\n")
            continue
        summary: dict[str, Any] = orjson.loads(summary_json) if summary_json else {}

        frames = rec.get("arena", {}).get("frames", []) or []
        upstream: list[tuple[int, str]] = []
        stages: dict[str, int] = {}
        for f in frames:
            origin = f.get("origin") or {}
            stage = str(origin.get("stage"))
            stages[stage] = stages.get(stage, 0) + 1
            if stage == "upstream-capture":
                upstream.append((int(f.get("sequence", 0)), str(f.get("handle"))))
        upstream.sort()

        transforms = rec.get("transforms", []) or []
        settled: list[dict[str, Any]] = []
        upstream_errors: list[dict[str, Any]] = []
        dispatches: list[dict[str, Any]] = []
        for dsp in rec.get("dispatches", []) or []:
            diags = dsp.get("diagnostics", []) or []
            kinds: dict[str, int] = {}
            for diag in diags:
                kind = str(diag.get("kind"))
                kinds[kind] = kinds.get(kind, 0) + 1
                if kind == "response.settled":
                    resp = (diag.get("data") or {}).get("response") or {}
                    settled.append(
                        {
                            "severity": diag.get("severity"),
                            "success": resp.get("success"),
                            "stop_reason": resp.get("stop_reason"),
                            "error": str(resp.get("error"))[:200] if resp.get("error") else None,
                            "usage": resp.get("usage"),
                        }
                    )
                elif kind == "upstream_error":
                    data = diag.get("data") or {}
                    upstream_errors.append(
                        {
                            "type": data.get("type"),
                            "status": data.get("status"),
                            "message": str(diag.get("message"))[:200],
                        }
                    )
            dispatches.append(
                {
                    "handle": dsp.get("handle"),
                    "verdict": dsp.get("verdict"),
                    "transport": dsp.get("transport"),
                    "timing": dsp.get("timing"),
                    "diag_kinds": kinds,
                }
            )

        terminal = rec.get("terminal") or {}
        out.write(
            orjson.dumps(
                {
                    "oid": oid,
                    "created_at": created_at,
                    "endpoint": summary.get("endpoint"),
                    "raw_path": summary.get("rawPath"),
                    "stream": summary.get("stream"),
                    "state": summary.get("state"),
                    "response_success": summary.get("responseSuccess"),
                    "request_model": summary.get("requestModel"),
                    "response_model": summary.get("responseModel"),
                    "attempt_count": summary.get("attemptCount"),
                    "n_frames": len(frames),
                    "stages": stages,
                    "n_upstream": len(upstream),
                    "tail_handles": [h for _, h in upstream[-TAIL:]],
                    "head_handles": [h for _, h in upstream[:3]],
                    "n_transforms": len(transforms),
                    "dispatches": dispatches,
                    "settled": settled,
                    "upstream_errors": upstream_errors,
                    "terminal_outcome": terminal.get("outcome"),
                    "candidate_reasons": [
                        c.get("reason") for c in (rec.get("candidates") or [])
                    ],
                }
            )
            + b"\n"
        )
        n += 1
        if n % 5000 == 0:
            print(f"  {n} ops", flush=True)
    out.close()
    print(f"done {db_path}: {n} operations -> {out_path}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    scan(sys.argv[1], sys.argv[2])
