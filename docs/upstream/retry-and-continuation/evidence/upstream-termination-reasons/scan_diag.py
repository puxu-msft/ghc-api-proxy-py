"""Scan timeline diagnostic / dispatch-settled / terminal events for upstream error literals."""
import sqlite3, glob, os, sys, json
from collections import Counter
import orjson, zstandard
PATS=["prompt token count","prompt is too long","context_length_exceeded","model_context_window_exceeded",
      "content_filter","off_topic","maximum context length","exceeds the limit of","incomplete","refusal",
      "context window","422","413"]
d=zstandard.ZstdDecompressor()
dbs=sys.argv[1:]
for p in dbs:
    con=sqlite3.connect(f"file:{p}?immutable=1",uri=True)
    hits=Counter(); samples={}
    statuses=Counter()
    ops=[r[0] for r in con.execute("select operation_id from v3_operations")]
    for oid in ops:
        ev=[]
        for (pg,) in con.execute("select payload_gz from v3_timeline_chunks where operation_id=? order by chunk_index",(oid,)):
            try: ev.extend(orjson.loads(d.decompress(pg)))
            except Exception: pass
        for e in ev:
            t=e.get("type")
            if t in ("frame","transform","payload"): continue
            s=json.dumps(e, ensure_ascii=False)
            if t=="dispatch-settled":
                v=e.get("value") or {}
                statuses[str(v.get("status") or v.get("httpStatus") or v.get("outcome"))]+=1
            for pat in PATS:
                if pat in s:
                    hits[pat]+=1
                    if pat not in samples:
                        i=s.find(pat); samples[pat]=(os.path.basename(p),oid,t,s[max(0,i-500):i+500])
    print("==",os.path.basename(p),"ops",len(ops),dict(hits))
    print("   dispatch-settled statuses:",dict(statuses.most_common(20)))
    for k,v in samples.items():
        print("   ---",k,v[0],v[1],v[2]); print("      ",v[3][:900])
    con.close()
