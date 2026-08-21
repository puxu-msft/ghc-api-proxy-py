"""Bulk-scan frame objects in one history db for termination-related literals."""
import sqlite3, sys, re, os
from collections import Counter
import zstandard

PATS = [
    b"incomplete_details", b"response.incomplete", b"response.failed",
    b"refusal", b"content_filter", b"max_output_tokens",
    b"context_length", b"context_window", b"model_context_window_exceeded",
    b"finish_reason", b'"status":"incomplete"', b'"status":"failed"',
    b'"status":"cancelled"', b'"status":"completed"', b'"status":"incomplete"',
    b"prompt_token_limit", b"off_topic", b"responsible_ai", b"content_filter_results",
]
TYPE_RE = re.compile(rb'"type"\s*:\s*"([a-z0-9_.\-]+)"')
FR_RE = re.compile(rb'"finish_reason"\s*:\s*"?([A-Za-z0-9_\-]+)"?')
REASON_RE = re.compile(rb'"reason"\s*:\s*"([A-Za-z0-9_\-]+)"')

def main(path, out):
    d = zstandard.ZstdDecompressor()
    con = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
    hits = Counter(); types = Counter(); fr = Counter(); reasons = Counter()
    samples = {}
    n = 0
    cur = con.execute("select hash, canonical_gz from v3_objects where kind='frame'")
    while True:
        rows = cur.fetchmany(5000)
        if not rows: break
        for h, blob in rows:
            n += 1
            try:
                b = d.decompress(blob)
            except Exception:
                continue
            m = TYPE_RE.search(b)
            if m: types[m.group(1)] += 1
            for p in PATS:
                if p in b:
                    hits[p] += 1
                    if p not in samples:
                        samples[p] = (h, b[:1500])
            for m in FR_RE.finditer(b):
                fr[m.group(1)] += 1
            if b"incomplete_details" in b or b"refusal" in b or b"content_filter" in b:
                for m in REASON_RE.finditer(b):
                    reasons[m.group(1)] += 1
    with open(out, "w") as f:
        f.write(f"db={path} frames={n}\n\nHITS\n")
        for p, c in hits.most_common():
            f.write(f"  {p.decode()}: {c}\n")
        f.write("\nFRAME TYPES\n")
        for t, c in types.most_common(80):
            f.write(f"  {t.decode()}: {c}\n")
        f.write("\nfinish_reason values\n")
        for t, c in fr.most_common():
            f.write(f"  {t.decode()}: {c}\n")
        f.write("\nreason values near incomplete/refusal/content_filter\n")
        for t, c in reasons.most_common():
            f.write(f"  {t.decode()}: {c}\n")
        f.write("\nSAMPLES\n")
        for p, (h, b) in samples.items():
            f.write(f"--- {p.decode()} hash={h}\n{b.decode('utf-8','replace')}\n\n")
    print("done", path, n)

main(sys.argv[1], sys.argv[2])
