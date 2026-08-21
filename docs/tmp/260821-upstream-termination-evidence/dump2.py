import sqlite3, sys, json, re
from collections import Counter
import orjson, zstandard
WANT = re.compile(rb'"type"\s*:\s*"(response\.incomplete|response\.failed|response\.cancelled|error)"')
d = zstandard.ZstdDecompressor()
KEEP = ("status","incomplete_details","error","id","model","object")
for path in sys.argv[1:]:
    con = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
    out=[]
    cur = con.execute("select hash, canonical_gz from v3_objects where kind='frame'")
    while True:
        rows = cur.fetchmany(5000)
        if not rows: break
        for h, blob in rows:
            try: b = d.decompress(blob)
            except Exception: continue
            if not WANT.search(b): continue
            try: fr = orjson.loads(b)
            except Exception: continue
            t = fr.get("type"); ev = fr.get("event"); syn = fr.get("synthetic")
            if t not in ("response.incomplete","response.failed","response.cancelled","error"): continue
            try: p = orjson.loads(fr.get("data") or "{}")
            except Exception: p = {}
            resp = p.get("response") if isinstance(p.get("response"), dict) else None
            summary = {k: resp.get(k) for k in KEEP if resp and k in resp} if resp else None
            if summary and "id" in summary: summary["id"] = "<opaque>"
            rec = {"hash": h[:12], "type": t, "event": ev, "synthetic": syn,
                   "resp": summary,
                   "payload_no_response": {k:v for k,v in p.items() if k!="response"} if t=="error" or resp is None else None}
            out.append(rec)
    print("="*70); print(path, "count", len(out))
    seen=Counter()
    for r in out:
        key = json.dumps({k:r[k] for k in ("type","event","synthetic","resp","payload_no_response")}, ensure_ascii=False, sort_keys=True)
        seen[key]+=1
    for k,v in seen.most_common():
        print(f"  x{v}  {k[:1200]}")
    con.close()
