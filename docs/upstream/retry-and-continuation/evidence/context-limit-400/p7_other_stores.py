#!/usr/bin/env python3
"""Read-only: scan every other sqlite store under ~/.local/share/copilot-api for the context-overflow literals.

Covers the pre-v3 archives and the side stores the v3 scan never touched. For each database it walks every
table and every column: TEXT is matched directly, BLOB is tried raw, then zstd, then gzip/zlib before being
given up on. Prints a per-database verdict so a zero is a *checked* zero rather than an unexamined one.
"""

from __future__ import annotations

import gzip
import re
import sqlite3
import zlib
from pathlib import Path

import zstandard

DEC = zstandard.ZstdDecompressor()
ROOT = Path.home() / ".local/share/copilot-api"
SKIP_PREFIX = "history-v3"
NEEDLES = (
    b"exceeds the context window",
    b"model_max_prompt_tokens",
    b"prompt is too long",
    b"prompt token count of",
    b"context_length_exceeded",
    b"maximum context",
    b"too many tokens",
)
PAT = re.compile(b"|".join(re.escape(n) for n in NEEDLES), re.I)


def texts(value: object) -> list[bytes]:
    if isinstance(value, str):
        return [value.encode("utf-8", "replace")]
    if not isinstance(value, bytes):
        return []
    out = [value]
    for name, fn in (("zstd", lambda b: DEC.decompress(b, max_output_size=200_000_000)), ("gzip", gzip.decompress), ("zlib", zlib.decompress)):
        try:
            out.append(fn(value))
        except Exception:  # noqa: BLE001 - a blob that is not this codec is the normal case, not an error
            continue
        break
    return out


targets = sorted(p for p in ROOT.rglob("*.db") if not p.name.startswith(SKIP_PREFIX))
print(f"{len(targets)} databases to scan (v3 history excluded, already covered)\n", flush=True)
for path in targets:
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        tables = [r[0] for r in db.execute("select name from sqlite_master where type='table'")]
    except sqlite3.Error as exc:
        print(f"SKIP {path}: {exc}")
        continue
    hits = 0
    rows_seen = 0
    for table in tables:
        try:
            cur = db.execute(f'select * from "{table}"')  # noqa: S608 - table name comes from sqlite_master
        except sqlite3.Error as exc:
            print(f"  {path.name}/{table}: {exc}")
            continue
        for row in cur:
            rows_seen += 1
            for value in row:
                for blob in texts(value):
                    m = PAT.search(blob)
                    if m:
                        hits += 1
                        start = max(0, m.start() - 200)
                        print(f"HIT {path.name}/{table}: ...{blob[start : m.end() + 300]!r}...", flush=True)
                        break
    print(f"== {path.relative_to(ROOT)}: tables={len(tables)} rows={rows_seen} hits={hits}", flush=True)
    db.close()
