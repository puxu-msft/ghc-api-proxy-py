#!/usr/bin/env python3
"""Read-only. Dump every field around a truncated reasoning item, with a completed-response control."""
from __future__ import annotations
import re, sqlite3, sys
from pathlib import Path
from typing import Any, cast
import orjson, zstandard

H = Path.home() / ".local/share/copilot-api"
DEC = zstandard.ZstdDecompressor()
EV = Path("/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260821-max-tokens-evidence")

def frames(db, op):
    row = db.execute("select manifest_gz from v3_operations where operation_id=?", (op,)).fetchone()
    if row is None: return []
    man = orjson.loads(DEC.decompress(row[0])); hashes = man["objectHashes"]
    events = []
    for (blob,) in db.execute("select payload_gz from v3_timeline_chunks where operation_id=? order by chunk_index", (op,)):
        events.extend(orjson.loads(DEC.decompress(blob)))
    derived = {o["handle"] for e in events if e.get("type")=="transform"
               for o in e.get("value",{}).get("outputs",[]) if o.get("kind")=="frame"}
    out=[]
    for e in sorted((e for e in events if e.get("type")=="frame"), key=lambda e:int(e["sequence"])):
        h=str(e.get("handle","")); 
        if h in derived: continue
        d=hashes.get(h)
        if d is None: continue
        st=db.execute("select canonical_gz from v3_objects where hash=?", (d,)).fetchone()
        if st is None: continue
        fr=orjson.loads(DEC.decompress(st[0])); raw=fr.get("data")
        if not isinstance(raw,str): continue
        try: pl=orjson.loads(raw)
        except orjson.JSONDecodeError: continue
        out.append((int(e["sequence"]), str(fr.get("event") or pl.get("type","")), cast(dict[str,Any],pl)))
    return out

def elide(o, n=70):
    if isinstance(o,str): return o if len(o)<=n else o[:n]+f"…<{len(o)} chars>"
    if isinstance(o,dict): return {k:elide(v,n) for k,v in o.items()}
    if isinstance(o,list): return [elide(v,n) for v in o]
    return o

def dump(tag, pl): print(f"  [{tag}] {orjson.dumps(elide(pl)).decode()}")

hits=[]
for line in (EV/"scan_hits.txt").read_text().splitlines():
    m=re.match(r"HIT (\S+) (\S+) ", line)
    if m: hits.append((m.group(1), m.group(2)))

reasoning_last=[]   # truncated: last output_item.done is a reasoning item
for dbname, op in hits:
    db=sqlite3.connect(f"file:{H/dbname}?mode=ro", uri=True)
    fs=frames(db,op)
    last=next((pl for _,n,pl in reversed(fs) if n=="response.output_item.done"), None)
    if last and (last.get("item") or {}).get("type")=="reasoning":
        reasoning_last.append((dbname,op,fs))
    db.close()

print(f"### 撞顶且最后一个 done 是 reasoning item 的样本数：{len(reasoning_last)}\n")
for dbname,op,fs in reasoning_last[:3]:
    print(f"===== {op} ({dbname})")
    tail=[(n,pl) for _,n,pl in fs if n.startswith("response.")][-6:]
    for n,pl in tail: dump(n,pl)
    print()

# ---- 正样本对照：正常收尾（response.completed）里的 reasoning item 长什么样 ----
print("### 正样本对照：response.completed 的响应里，reasoning item 的 output_item.done\n")
shown=0
for dbname in sorted({d for d,_ in hits}):
    db=sqlite3.connect(f"file:{H/dbname}?mode=ro", uri=True)
    for (op,) in db.execute("select operation_id from v3_operations limit 4000"):
        if shown>=2: break
        try: fs=frames(db,op)
        except Exception: continue
        if not any(n=="response.completed" for _,n,_ in fs): continue
        done=[pl for _,n,pl in fs if n=="response.output_item.done" and (pl.get("item") or {}).get("type")=="reasoning"]
        if not done: continue
        print(f"===== {op} ({dbname})  [response.completed]")
        dump("response.output_item.done(reasoning)", done[-1]); print()
        shown+=1
    db.close()
    if shown>=2: break
