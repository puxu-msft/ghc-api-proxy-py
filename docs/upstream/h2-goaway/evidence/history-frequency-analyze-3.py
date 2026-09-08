#!/usr/bin/env python3
"""Part 3: time series, deploy-window check, model effect conditioned on duration,
and a dump of the largest simultaneous-failure events."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

CO = Path("/home/xp/.local/share/copilot-api")
DBS = [
    "history-v3-260807.db", "history-v3-260809.db", "history-v3-260811.db",
    "history-v3.db", "history-v3-20260815-183721.db",
    "history-v3-20260816-160151.db", "history-v3-20260817-050754.db",
    "history-v3-20260818-044224.db",
]
MIT = int(datetime(2026, 7, 22, 23, 10, 30, tzinfo=timezone.utc).timestamp() * 1000)
PATS = [("nghttp2_cancel", "NGHTTP2_CANCEL"), ("nghttp2_other", "NGHTTP2_"),
        ("closed_before_response", "upstream stream closed before any response"),
        ("truncated", "upstream stream truncated"),
        ("tls_timeout", "TLS connect timeout"), ("dns", "getaddrinfo")]


def ts(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def cls(r):
    e = r.get("responseError")
    if e is None:
        return None
    if not isinstance(e, str):
        e = json.dumps(e)
    for lab, n in PATS:
        if n.lower() in e.lower():
            return lab
    return None


def load():
    rows = []
    for name in DBS:
        con = sqlite3.connect(f"file://{CO / name}?mode=ro", uri=True)
        try:
            for (sj,) in con.execute("select summary_json from v3_operation_summaries"):
                if sj:
                    rows.append(json.loads(sj))
        finally:
            con.close()
    rows.sort(key=lambda r: r.get("startedAt") or 0)
    return [r for r in rows if r.get("operationKind") == "generation"]


gens = load()
tr = [r for r in gens if cls(r)]

print("=" * 74)
print("G. hourly series on the two worst days (UTC)")
print("=" * 74)
for day in ("2026-08-06", "2026-08-07", "2026-08-08"):
    hall, htr = Counter(), Counter()
    for r in gens:
        s = ts(r["startedAt"])
        if s[:10] == day:
            hall[int(s[11:13])] += 1
    for r in tr:
        s = ts(r["startedAt"])
        if s[:10] == day:
            htr[int(s[11:13])] += 1
    if not hall:
        continue
    print(f"  {day}")
    for h in range(24):
        if hall[h]:
            bar = "#" * min(60, htr[h])
            print(f"    {h:02d}h n={hall[h]:5d} fail={htr[h]:3d} "
                  f"{100*htr[h]/hall[h]:5.2f}% {bar}")
print()

print("=" * 74)
print("H. does the failure hour align across days? (deploy-window test)")
print("=" * 74)
hall, htr = Counter(), Counter()
for r in gens:
    hall[int(ts(r["startedAt"])[11:13])] += 1
for r in tr:
    htr[int(ts(r["startedAt"])[11:13])] += 1
tot_n, tot_f = sum(hall.values()), sum(htr.values())
base = tot_f / tot_n
print(f"  overall rate {100*base:.3f}%   (chi-square-ish per-hour deviation)")
chi = 0.0
for h in range(24):
    if not hall[h]:
        continue
    exp = hall[h] * base
    chi += (htr[h] - exp) ** 2 / max(exp, 1e-9)
    flag = "  <<<" if htr[h] > exp * 1.6 and htr[h] >= 15 else ""
    print(f"    {h:02d}h n={hall[h]:6d} obs={htr[h]:4d} exp={exp:7.1f} "
          f"ratio={htr[h]/max(exp,1e-9):5.2f}{flag}")
print(f"  chi2 = {chi:.1f} on 23 dof (critical 0.1% ~ 49.7)")
print()

print("=" * 74)
print("I. model effect, conditioned on duration bucket")
print("=" * 74)
edges = [0, 20, 80, 320, 10**9]
models = ["claude-opus-5", "claude-sonnet-5", "gpt-5.6-sol", "gpt-5.6-terra"]
print("   bucket_s      " + "".join(f"{m:>22s}" for m in models))
for i in range(len(edges) - 1):
    lo, hi = edges[i], edges[i + 1]
    cells = []
    for m in models:
        sel = [r for r in gens if r.get("responseModel") == m
               and lo <= (r.get("durationMs") or 0) / 1000 < hi]
        f = [r for r in sel if cls(r)]
        cells.append(f"{len(f):4d}/{len(sel):6d}={100*len(f)/max(1,len(sel)):5.2f}%")
    print(f"   [{lo:5d},{hi if hi<10**8 else 9999:5d}) " + "".join(f"{c:>22s}" for c in cells))
print()

print("=" * 74)
print("J. largest simultaneous-failure events, ALL failed kinds, same pid, 3s")
print("=" * 74)
bad = [r for r in gens if r.get("state") == "failed"]
groups = defaultdict(list)
for r in bad:
    groups[r.get("pid")].append(r)
events = []
for pid, rs in groups.items():
    rs.sort(key=lambda r: r.get("endedAt") or r["startedAt"])
    cur = []
    for r in rs:
        e = r.get("endedAt") or r["startedAt"]
        if cur and e - (cur[-1].get("endedAt") or cur[-1]["startedAt"]) <= 3000:
            cur.append(r)
        else:
            if cur:
                events.append(cur)
            cur = [r]
    if cur:
        events.append(cur)
events.sort(key=len, reverse=True)
for ev in events[:10]:
    e0 = ev[0].get("endedAt") or ev[0]["startedAt"]
    era = "PRE-mitigation" if ev[0]["startedAt"] < MIT else "post-mitigation"
    print(f"  n={len(ev)}  {ts(e0)}  pid={ev[0].get('pid')}  [{era}]")
    for r in ev:
        err = r.get("responseError")
        if not isinstance(err, str):
            err = json.dumps(err)
        print(f"      start={ts(r['startedAt'])} dur={(r.get('durationMs') or 0)/1000:8.1f}s "
              f"rq={r.get('requestBytes'):>9} rs={str(r.get('responseBytes')):>9} "
              f"{r.get('responseModel')} :: {err[:70]}")
    print()

print("=" * 74)
print("K. rate of *multi-victim* transport events per day of data")
print("=" * 74)
for label, sel in (("PRE ", lambda r: r["startedAt"] < MIT),
                   ("POST", lambda r: r["startedAt"] >= MIT)):
    g = [r for r in gens if sel(r)]
    t = [r for r in tr if sel(r)]
    span_days = (g[-1]["startedAt"] - g[0]["startedAt"]) / 86400000
    gr = defaultdict(list)
    for r in t:
        gr[r.get("pid")].append(r)
    ev = []
    for pid, rs in gr.items():
        rs.sort(key=lambda r: r.get("endedAt") or r["startedAt"])
        cur = []
        for r in rs:
            e = r.get("endedAt") or r["startedAt"]
            if cur and e - (cur[-1].get("endedAt") or cur[-1]["startedAt"]) <= 3000:
                cur.append(r)
            else:
                if cur:
                    ev.append(cur)
                cur = [r]
        if cur:
            ev.append(cur)
    multi = [c for c in ev if len(c) >= 2]
    print(f"  {label} span={span_days:.2f}d  gens={len(g)}  "
          f"transport-fails={len(t)} ({len(t)/span_days:.1f}/day)  "
          f"multi-victim events={len(multi)} ({len(multi)/span_days:.2f}/day)  "
          f"victims/event={sum(len(c) for c in multi)/max(1,len(multi)):.2f}")
