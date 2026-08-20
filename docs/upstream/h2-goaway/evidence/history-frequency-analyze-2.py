#!/usr/bin/env python3
"""Part 2: blast-radius / hazard analysis, split at the 2026-07-22 mitigation.

Read-only (?mode=ro). See analyze.py for the base pass.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

CO = Path("/home/xp/.local/share/copilot-api")
DBS = [
    "history-v3-260807.db",
    "history-v3-260809.db",
    "history-v3-260811.db",
    "history-v3.db",
    "history-v3-20260815-183721.db",
    "history-v3-20260816-160151.db",
    "history-v3-20260817-050754.db",
    "history-v3-20260818-044224.db",
]

# `feat(transport): cap concurrent streams per h2 session (default 1)`
# b5892380f, authored 2026-07-22 23:10:30 +0000. Deployment time is unknown;
# treat the boundary as approximate.
MITIGATION_MS = int(datetime(2026, 7, 22, 23, 10, 30, tzinfo=timezone.utc).timestamp() * 1000)

TRANSPORT_PATTERNS = [
    ("nghttp2_cancel", "NGHTTP2_CANCEL"),
    ("nghttp2_other", "NGHTTP2_"),
    ("closed_before_response", "upstream stream closed before any response"),
    ("truncated", "upstream stream truncated"),
    ("tls_timeout", "TLS connect timeout"),
    ("dns", "getaddrinfo"),
    ("econnreset", "ECONNRESET"),
    ("socket_hangup", "socket hang up"),
    ("epipe", "EPIPE"),
]


def ts(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def classify(row):
    err = row.get("responseError")
    if err is None:
        return None
    if not isinstance(err, str):
        err = json.dumps(err)
    low = err.lower()
    for label, needle in TRANSPORT_PATTERNS:
        if needle.lower() in low:
            return label
    return None


def load():
    rows = []
    for name in DBS:
        con = sqlite3.connect(f"file://{CO / name}?mode=ro", uri=True)
        try:
            for (sj,) in con.execute("select summary_json from v3_operation_summaries"):
                if sj:
                    d = json.loads(sj)
                    d["_db"] = name
                    rows.append(d)
        finally:
            con.close()
    rows.sort(key=lambda r: r.get("startedAt") or 0)
    return [r for r in rows if r.get("operationKind") == "generation"]


def clusters_of(rows, window_ms=2000, by_pid=True):
    """Group failures whose END times are within window_ms, optionally per pid."""
    out = []
    groups = defaultdict(list)
    for r in rows:
        key = r.get("pid") if by_pid else 0
        groups[key].append(r)
    for key, rs in groups.items():
        rs = sorted(rs, key=lambda r: r.get("endedAt") or r["startedAt"])
        cur = []
        for r in rs:
            e = r.get("endedAt") or r["startedAt"]
            if cur and e - (cur[-1].get("endedAt") or cur[-1]["startedAt"]) <= window_ms:
                cur.append(r)
            else:
                if cur:
                    out.append(cur)
                cur = [r]
        if cur:
            out.append(cur)
    return out


def main():
    gens = load()
    tr = [r for r in gens if classify(r)]

    print("=" * 70)
    print("A. BLAST RADIUS: before vs after the 2026-07-22 N=1 mitigation")
    print("=" * 70)
    print(f"boundary = {ts(MITIGATION_MS)} UTC (commit b5892380f author date)")
    print()
    for label, sel in (
        ("PRE  (h2 multiplex, all concurrent streams share 1 session)",
         lambda r: r["startedAt"] < MITIGATION_MS),
        ("POST (N=1, one h2 session per concurrent request)",
         lambda r: r["startedAt"] >= MITIGATION_MS),
    ):
        g = [r for r in gens if sel(r)]
        t = [r for r in tr if sel(r)]
        print(f"-- {label}")
        if not g:
            print("   (no data)")
            continue
        print(f"   window {ts(g[0]['startedAt'])} .. {ts(g[-1]['startedAt'])}")
        print(f"   generations={len(g)}  transport-fails={len(t)} "
              f"({100*len(t)/len(g):.2f}%)")
        print(f"   classes: {dict(Counter(classify(r) for r in t))}")
        cls = clusters_of(t, by_pid=True)
        hist = Counter(len(c) for c in cls)
        multi = sum(len(c) for c in cls if len(c) >= 2)
        print(f"   same-pid clusters (2s): sizes={dict(sorted(hist.items()))} "
              f"-> {multi}/{len(t)} = "
              f"{100*multi/max(1,len(t)):.1f}% of fails are in a batch")
        for c in sorted([c for c in cls if len(c) >= 2], key=len, reverse=True)[:8]:
            e0 = c[0].get("endedAt") or c[0]["startedAt"]
            print(f"      n={len(c)} @ {ts(e0)} pid={c[0].get('pid')} "
                  f"{dict(Counter(classify(x) for x in c))} "
                  f"durs={[round((x.get('durationMs') or 0)/1000,1) for x in c]}")
        print()

    print("=" * 70)
    print("B. same-second batch detection, ALL failure kinds (not just transport)")
    print("=" * 70)
    bad = [r for r in gens if r.get("state") in ("failed",)]
    for label, sel in (
        ("PRE ", lambda r: r["startedAt"] < MITIGATION_MS),
        ("POST", lambda r: r["startedAt"] >= MITIGATION_MS),
    ):
        b = [r for r in bad if sel(r)]
        cls = clusters_of(b, by_pid=True)
        multi = sum(len(c) for c in cls if len(c) >= 2)
        print(f"  {label} failed={len(b):4d}  in-batch={multi:4d} "
              f"({100*multi/max(1,len(b)):.1f}%)  "
              f"sizes={dict(sorted(Counter(len(c) for c in cls).items()))}")
    print()

    print("=" * 70)
    print("C. HAZARD: is the failure rate proportional to time on the wire?")
    print("=" * 70)
    print("   For each duration bucket: among generations that were still")
    print("   running at the bucket's start, what fraction died inside it?")
    print()
    edges = [0, 5, 10, 20, 40, 80, 160, 320, 640, 10**9]
    ok = [r for r in gens if r.get("state") == "completed"]
    print("   bucket_s     at_risk   died   hazard/req   hazard_per_sec")
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        at_risk = sum(1 for r in gens
                      if (r.get("durationMs") or 0) / 1000 >= lo)
        died = sum(1 for r in tr
                   if lo <= (r.get("durationMs") or 0) / 1000 < hi)
        if at_risk == 0:
            continue
        width = min(hi, 1200) - lo
        h = died / at_risk
        print(f"   [{lo:5d},{hi if hi<10**8 else 9999:5d})  {at_risk:8d} {died:6d} "
              f"{h:11.5f}   {h/max(width,1):.2e}")
    print()

    print("=" * 70)
    print("D. requestBytes AFTER conditioning on duration bucket")
    print("=" * 70)
    print("   duration bucket | completed med rq | fail med rq | fail n")
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        c = sorted(r["requestBytes"] for r in ok
                   if lo <= (r.get("durationMs") or 0) / 1000 < hi
                   and isinstance(r.get("requestBytes"), int))
        f = sorted(r["requestBytes"] for r in tr
                   if lo <= (r.get("durationMs") or 0) / 1000 < hi
                   and isinstance(r.get("requestBytes"), int))
        if not f:
            continue
        print(f"   [{lo:5d},{hi if hi<10**8 else 9999:5d})  "
              f"{(c[len(c)//2] if c else 0):>12,}  {f[len(f)//2]:>12,}  {len(f):5d}")
    print()

    print("=" * 70)
    print("E. how far had the response got when it died?")
    print("=" * 70)
    for k in sorted({classify(r) for r in tr}):
        rs = [r for r in tr if classify(r) == k]
        rb = sorted(r.get("responseBytes") or 0 for r in rs)
        n = len(rb)
        tiny = sum(1 for v in rb if v < 2048)
        print(f"   {k:24s} n={n:4d}  respBytes p10={rb[n//10]:>10,} "
              f"med={rb[n//2]:>10,} p90={rb[9*n//10]:>10,}  <2KB: {tiny}")
    print()

    print("=" * 70)
    print("F. concurrency at the moment of failure (same pid, overlapping)")
    print("=" * 70)
    by_pid = defaultdict(list)
    for r in gens:
        by_pid[r.get("pid")].append(r)
    conc = []
    for r in tr:
        end = r.get("endedAt") or r["startedAt"]
        peers = sum(1 for p in by_pid[r.get("pid")]
                    if p is not r
                    and p["startedAt"] <= end <= (p.get("endedAt") or p["startedAt"]))
        conc.append(peers)
    print(f"   concurrent peers in flight when a transport failure hit: "
          f"{dict(sorted(Counter(conc).items()))}")
    print(f"   mean={sum(conc)/max(1,len(conc)):.2f}")
    # baseline: same measure for a sample of completed
    base = []
    for r in ok[::37]:
        end = r.get("endedAt") or r["startedAt"]
        peers = sum(1 for p in by_pid[r.get("pid")]
                    if p is not r
                    and p["startedAt"] <= end <= (p.get("endedAt") or p["startedAt"]))
        base.append(peers)
    print(f"   baseline (every 37th completed, n={len(base)}): "
          f"mean={sum(base)/max(1,len(base)):.2f} "
          f"{dict(sorted(Counter(base).items())[:8])}")


if __name__ == "__main__":
    main()
