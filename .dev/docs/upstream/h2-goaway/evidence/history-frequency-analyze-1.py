#!/usr/bin/env python3
"""One-off forensic analysis of upstream transport interruptions.

Read-only. Opens every history DB with sqlite3 URI ?mode=ro.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
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

LOCAL = timezone.utc  # host runs UTC (verified: timedatectl -> Etc/UTC)


def ts(ms: int | None) -> str:
    if ms is None:
        return "-"
    return datetime.fromtimestamp(ms / 1000, LOCAL).strftime("%Y-%m-%d %H:%M:%S")


def load() -> list[dict]:
    rows: list[dict] = []
    for name in DBS:
        p = CO / name
        con = sqlite3.connect(f"file://{p}?mode=ro", uri=True)
        try:
            cur = con.execute(
                "select operation_id, summary_json from v3_operation_summaries"
            )
            for op_id, sj in cur:
                if not sj:
                    continue
                d = json.loads(sj)
                d["_db"] = name
                d["_op"] = op_id
                rows.append(d)
        finally:
            con.close()
    rows.sort(key=lambda r: r.get("startedAt") or 0)
    return rows


# ---- classification -------------------------------------------------------

TRANSPORT_PATTERNS = [
    ("nghttp2_cancel", "NGHTTP2_CANCEL"),
    ("nghttp2_internal", "NGHTTP2_INTERNAL_ERROR"),
    ("nghttp2_other", "NGHTTP2_"),
    ("closed_before_response", "upstream stream closed before any response"),
    ("truncated", "upstream stream truncated"),
    ("tls_timeout", "TLS connect timeout"),
    ("dns", "getaddrinfo"),
    ("econnreset", "ECONNRESET"),
    ("socket_hangup", "socket hang up"),
    ("epipe", "EPIPE"),
    ("goaway", "GOAWAY"),
]


def classify(row: dict) -> str | None:
    """Return a transport-interruption class, or None if not transport."""
    err = row.get("responseError")
    if err is None:
        return None
    if not isinstance(err, str):
        err = json.dumps(err)
    for label, needle in TRANSPORT_PATTERNS:
        if needle.lower() in err.lower():
            return label
    return None


def main() -> None:
    rows = load()
    gens = [r for r in rows if r.get("operationKind") == "generation"]
    print(f"total operations: {len(rows)}")
    print(f"generation operations: {len(gens)}")
    print(f"window: {ts(gens[0]['startedAt'])} .. {ts(gens[-1]['startedAt'])}")
    print()

    # per-db coverage
    print("== per-db coverage (generation ops) ==")
    bydb: dict[str, list[dict]] = defaultdict(list)
    for r in gens:
        bydb[r["_db"]].append(r)
    for name in DBS:
        rs = bydb.get(name, [])
        if not rs:
            print(f"{name:36s} 0")
            continue
        tr = [r for r in rs if classify(r)]
        print(
            f"{name:36s} n={len(rs):6d}  {ts(rs[0]['startedAt'])} .. "
            f"{ts(rs[-1]['startedAt'])}  transport-fail={len(tr):4d} "
            f"({100*len(tr)/len(rs):.2f}%)"
        )
    print()

    # class histogram
    print("== transport-interruption class histogram (all time) ==")
    c = Counter(classify(r) for r in gens if classify(r))
    for k, v in c.most_common():
        print(f"  {k:24s} {v}")
    total_tr = sum(c.values())
    print(f"  TOTAL {total_tr}  = {100*total_tr/len(gens):.3f}% of generations")
    print()

    # daily rate
    print("== per-day: generations / transport-fails / rate ==")
    day_all: Counter = Counter()
    day_tr: Counter = Counter()
    for r in gens:
        d = ts(r["startedAt"])[:10]
        day_all[d] += 1
        if classify(r):
            day_tr[d] += 1
    for d in sorted(day_all):
        n, t = day_all[d], day_tr[d]
        print(f"  {d}  n={n:6d}  transport-fail={t:4d}  {100*t/n:6.2f}%")
    print()

    # clustering: transport failures ending within the same second / 2s window
    print("== clustering of transport failures by END time ==")
    tr_rows = [r for r in gens if classify(r)]
    tr_rows.sort(key=lambda r: r.get("endedAt") or r.get("startedAt") or 0)
    clusters: list[list[dict]] = []
    cur: list[dict] = []
    WINDOW_MS = 2000
    for r in tr_rows:
        e = r.get("endedAt") or r.get("startedAt")
        if cur and e - (cur[-1].get("endedAt") or cur[-1]["startedAt"]) <= WINDOW_MS:
            cur.append(r)
        else:
            if cur:
                clusters.append(cur)
            cur = [r]
    if cur:
        clusters.append(cur)
    size_hist = Counter(len(cl) for cl in clusters)
    print(f"  window={WINDOW_MS}ms  clusters={len(clusters)}  members={len(tr_rows)}")
    for size in sorted(size_hist):
        print(f"    size {size:2d}: {size_hist[size]} clusters "
              f"({size*size_hist[size]} failures)")
    multi = [cl for cl in clusters if len(cl) >= 2]
    in_multi = sum(len(cl) for cl in multi)
    print(f"  failures in clusters of >=2: {in_multi}/{len(tr_rows)} "
          f"= {100*in_multi/max(1,len(tr_rows)):.1f}%")
    print()
    print("  -- largest 15 clusters --")
    for cl in sorted(multi, key=len, reverse=True)[:15]:
        e0 = cl[0].get("endedAt") or cl[0]["startedAt"]
        e1 = cl[-1].get("endedAt") or cl[-1]["startedAt"]
        pids = sorted({r.get("pid") for r in cl})
        kinds = Counter(classify(r) for r in cl)
        print(f"    n={len(cl):2d}  {ts(e0)} .. {ts(e1)}  pids={pids}  {dict(kinds)}")
    print()

    # Null hypothesis: are clusters more than chance?
    print("== clustering vs. chance (per-day Poisson expectation) ==")
    print("  day        fails  span_s   E[pairs<=2s]  obs_pairs_in_multiclusters")
    for d in sorted(day_tr):
        if day_tr[d] < 2:
            continue
        rs = [r for r in tr_rows if ts(r.get("endedAt") or r["startedAt"])[:10] == d]
        n = len(rs)
        span = 86400.0
        # expected number of ordered pairs within 2s if uniform over the day
        exp_pairs = n * (n - 1) / 2 * (2 * WINDOW_MS / 1000) / span
        obs = 0
        for cl in clusters:
            e0 = cl[0].get("endedAt") or cl[0]["startedAt"]
            if ts(e0)[:10] != d:
                continue
            if len(cl) >= 2:
                obs += len(cl) * (len(cl) - 1) / 2
        print(f"  {d}  {n:5d}  {span:7.0f}  {exp_pairs:12.3f}   {obs:.0f}")
    print()

    # size / duration correlation
    print("== requestBytes / durationMs: transport-fail vs completed ==")

    def stats(vals: list[float], label: str) -> None:
        if not vals:
            print(f"  {label}: (none)")
            return
        vals = sorted(vals)
        n = len(vals)

        def q(p: float) -> float:
            return vals[min(n - 1, int(p * n))]

        print(
            f"  {label:28s} n={n:6d} p10={q(.1):>12,.0f} med={q(.5):>12,.0f} "
            f"p90={q(.9):>12,.0f} p99={q(.99):>12,.0f} max={vals[-1]:>12,.0f}"
        )

    ok = [r for r in gens if r.get("state") == "completed"]
    for field in ("requestBytes", "durationMs", "messageCount"):
        stats([r[field] for r in ok if isinstance(r.get(field), (int, float))],
              f"completed.{field}")
        stats([r[field] for r in tr_rows if isinstance(r.get(field), (int, float))],
              f"transportfail.{field}")
    print()

    # by model / endpoint / stream
    print("== transport-fail rate by requestModel (n>=200) ==")
    by = defaultdict(lambda: [0, 0])
    for r in gens:
        k = str(r.get("requestModel"))
        by[k][0] += 1
        if classify(r):
            by[k][1] += 1
    for k, (n, t) in sorted(by.items(), key=lambda kv: -kv[1][0]):
        if n >= 200:
            print(f"  {k:28s} n={n:6d} fail={t:4d} {100*t/n:6.2f}%")
    print()

    print("== transport-fail rate by responseModel (n>=200) ==")
    by = defaultdict(lambda: [0, 0])
    for r in gens:
        k = str(r.get("responseModel"))
        by[k][0] += 1
        if classify(r):
            by[k][1] += 1
    for k, (n, t) in sorted(by.items(), key=lambda kv: -kv[1][0]):
        if n >= 200:
            print(f"  {k:28s} n={n:6d} fail={t:4d} {100*t/n:6.2f}%")
    print()

    print("== transport-fail rate by endpoint ==")
    by = defaultdict(lambda: [0, 0])
    for r in gens:
        k = str(r.get("endpoint"))
        by[k][0] += 1
        if classify(r):
            by[k][1] += 1
    for k, (n, t) in sorted(by.items(), key=lambda kv: -kv[1][0]):
        print(f"  {k:28s} n={n:6d} fail={t:4d} {100*t/n:6.2f}%")
    print()

    print("== hour-of-day distribution (local +08) ==")
    hall: Counter = Counter()
    htr: Counter = Counter()
    for r in gens:
        h = int(ts(r["startedAt"])[11:13])
        hall[h] += 1
        if classify(r):
            htr[h] += 1
    for h in range(24):
        n, t = hall[h], htr[h]
        if n:
            print(f"  {h:02d}h  n={n:6d} fail={t:4d} {100*t/n:6.2f}%")
    print()

    print("== responseBytes at failure (how much had arrived) ==")
    stats([r["responseBytes"] for r in tr_rows
           if isinstance(r.get("responseBytes"), (int, float))],
          "transportfail.responseBytes")
    zero = sum(1 for r in tr_rows if r.get("responseBytes") in (0, None))
    print(f"  zero-or-missing responseBytes: {zero}/{len(tr_rows)}")
    print()

    print("== attemptCount among transport failures ==")
    print("  ", dict(Counter(r.get("attemptCount") for r in tr_rows)))
    print("== attemptCount among completed ==")
    print("  ", dict(Counter(r.get("attemptCount") for r in ok).most_common(6)))


if __name__ == "__main__":
    main()
