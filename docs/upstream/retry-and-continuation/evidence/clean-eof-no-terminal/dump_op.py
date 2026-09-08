"""Phase C: dump one operation's upstream frames and judge whether every block closed.

For each `upstream-capture` frame, in sequence order: the SSE event name plus the few structural fields that decide block completeness. Free text is never printed — the databases hold the operator's own conversations.

Responses leg: a draft opens at `response.output_item.added` and closes at `response.output_item.done`, which is the only thing this project's assembler treats as a completed block (`src/app/pipeline/delivery/assembler.py`).
Anthropic leg: `content_block_start` opens, `content_block_stop` closes.

usage: dump_op.py <db path> <operation id> [<operation id> ...]
"""

from __future__ import annotations

import sqlite3
import sys
from typing import Any

import orjson
import zstandard

LEGAL_TERMINAL = {"response.completed", "response.incomplete", "message_stop"}


def upstream_handles(rec: dict[str, Any]) -> list[tuple[int, str, str]]:
    out: list[tuple[int, str, str]] = []
    for frame in rec.get("arena", {}).get("frames", []) or []:
        origin = frame.get("origin") or {}
        if origin.get("stage") == "upstream-capture":
            out.append((int(frame.get("sequence", 0)), str(frame.get("handle")), str(origin.get("dispatch"))))
    out.sort()
    return out


def describe(name: str, payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    bits: list[str] = []
    for key in ("output_index", "index", "item_id", "sequence_number"):
        if key in payload:
            bits.append(f"{key}={payload[key]!r}")
    item = payload.get("item")
    if isinstance(item, dict):
        bits.append(f"item.type={item.get('type')!r} item.status={item.get('status')!r} item.id={item.get('id')!r}")
        args = item.get("arguments")
        if isinstance(args, str):
            bits.append(f"args_len={len(args)}")
    block = payload.get("content_block")
    if isinstance(block, dict):
        bits.append(f"block.type={block.get('type')!r}")
    part = payload.get("part")
    if isinstance(part, dict):
        bits.append(f"part.type={part.get('type')!r}")
    delta = payload.get("delta")
    if isinstance(delta, dict):
        bits.append(f"delta.type={delta.get('type')!r} stop_reason={delta.get('stop_reason')!r}")
    response = payload.get("response")
    if isinstance(response, dict):
        bits.append(f"resp.status={response.get('status')!r} incomplete={response.get('incomplete_details')!r} error={response.get('error')!r}")
        usage = response.get("usage")
        if usage is not None:
            bits.append(f"usage={orjson.dumps(usage).decode()}")
        output = response.get("output")
        if isinstance(output, list):
            bits.append(f"output_items={len(output)} kinds={[(o.get('type'), o.get('status')) for o in output if isinstance(o, dict)]}")
    if "usage" in payload and not isinstance(payload.get("response"), dict):
        bits.append(f"usage={orjson.dumps(payload.get('usage')).decode()}")
    return " ".join(bits)


def dump(db_path: str, oid: str) -> None:
    con = sqlite3.connect(f"file:{db_path}?immutable=1", uri=True)
    dec = zstandard.ZstdDecompressor()
    row = con.execute(
        "select manifest_gz, summary_json, created_at from v3_operations where operation_id=?", (oid,)
    ).fetchone()
    if row is None:
        print(f"== {oid}: NOT FOUND in {db_path}")
        return
    manifest = orjson.loads(dec.decompress(row[0]))
    rec = manifest["record"]
    hashes = manifest["objectHashes"]
    summary = orjson.loads(row[1]) if row[1] else {}
    print(f"===== {oid}  db={db_path.rsplit('/', 1)[-1]}")
    print(
        f"  created_at={row[2]} endpoint={summary.get('endpoint')!r} rawPath={summary.get('rawPath')!r} stream={summary.get('stream')!r}"
        f" requestModel={summary.get('requestModel')!r} responseModel={summary.get('responseModel')!r} state={summary.get('state')!r}"
        f" success={summary.get('responseSuccess')!r} attempts={summary.get('attemptCount')!r} durationMs={summary.get('durationMs')!r}"
        f" usage={orjson.dumps(summary.get('usage')).decode()}"
    )
    print(f"  n_transforms={len(rec.get('transforms') or [])} terminal={orjson.dumps((rec.get('terminal') or {}).get('outcome')).decode()}")
    for dsp in rec.get("dispatches") or []:
        print(f"  dispatch {dsp.get('handle')} verdict={dsp.get('verdict')!r} transport={dsp.get('transport')!r} timing={orjson.dumps(dsp.get('timing')).decode()}")
        for diag in dsp.get("diagnostics") or []:
            kind = diag.get("kind")
            if kind in {"response.settled", "upstream_error", "retry", "response.headers"}:
                data = diag.get("data") or {}
                if kind == "response.headers":
                    headers = data.get("headers") or {}
                    print(f"    diag {kind}: content-type={headers.get('content-type')!r} status_hint={headers.get('x-github-request-id') is not None}")
                else:
                    print(f"    diag {kind} [{diag.get('severity')}]: {orjson.dumps(data).decode()[:400]}")

    opened: dict[Any, Any] = {}
    closed: dict[Any, Any] = {}
    ab_open: dict[Any, Any] = {}
    ab_closed: dict[Any, Any] = {}
    counts: dict[str, int] = {}
    frames = upstream_handles(rec)
    print(f"  upstream frames: {len(frames)}")
    for seq, handle, dispatch in frames:
        digest = hashes.get(handle)
        stored = con.execute("select canonical_gz from v3_objects where hash=?", (digest,)).fetchone() if digest else None
        if stored is None:
            print(f"   seq={seq} {handle} <object missing>")
            continue
        frame = orjson.loads(dec.decompress(stored[0]))
        raw = frame.get("data")
        payload: Any = None
        if isinstance(raw, str):
            if raw.strip() == "[DONE]":
                payload = "[DONE]"
            else:
                try:
                    payload = orjson.loads(raw)
                except orjson.JSONDecodeError:
                    payload = None
        name = frame.get("event") or (payload.get("type") if isinstance(payload, dict) else str(payload))
        counts[str(name)] = counts.get(str(name), 0) + 1
        if name == "response.output_item.added":
            opened[payload.get("output_index")] = payload.get("item", {}).get("type")
        elif name == "response.output_item.done":
            closed[payload.get("output_index")] = payload.get("item", {}).get("type")
        elif name == "content_block_start":
            ab_open[payload.get("index")] = (payload.get("content_block") or {}).get("type")
        elif name == "content_block_stop":
            ab_closed[payload.get("index")] = True
        detail = describe(str(name), payload)
        head = len(frames) - 1
        if seq == frames[head][0] or len(frames) <= 60 or name not in {
            "response.output_text.delta",
            "response.reasoning_summary_text.delta",
            "response.function_call_arguments.delta",
            "content_block_delta",
        }:
            print(f"   seq={seq} [{dispatch}] {name} {detail[:600]}")
    print(f"  event counts: {orjson.dumps(dict(sorted(counts.items()))).decode()}")
    print(f"  responses items: opened={sorted(map(str, opened))} closed={sorted(map(str, closed))} UNCLOSED={sorted(map(str, set(opened) - set(closed)))}")
    print(f"  anthropic blocks: opened={sorted(map(str, ab_open))} closed={sorted(map(str, ab_closed))} UNCLOSED={sorted(map(str, set(ab_open) - set(ab_closed)))}")
    print(f"  legal terminal present: {any(k in LEGAL_TERMINAL for k in counts)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)
    for target in sys.argv[2:]:
        dump(sys.argv[1], target)
