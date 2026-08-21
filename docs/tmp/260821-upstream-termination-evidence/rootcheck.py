import sqlite3, sys, re
import orjson, zstandard
WANT=b'"type":"response.incomplete"'
d=zstandard.ZstdDecompressor()
for path in sys.argv[1:]:
    con=sqlite3.connect(f"file:{path}?immutable=1",uri=True)
    targets=set()
    cur=con.execute("select hash, canonical_gz from v3_objects where kind='frame'")
    while True:
        rows=cur.fetchmany(5000)
        if not rows: break
        for h,blob in rows:
            try: b=d.decompress(blob)
            except Exception: continue
            if WANT in b.replace(b' ',b''): targets.add(h)
    print(path,"target hashes",len(targets))
    root=0; derived=0; ops=set()
    for (oid,mg) in con.execute("select operation_id, manifest_gz from v3_operations"):
        try: man=orjson.loads(d.decompress(mg))
        except Exception: continue
        hashes=man.get("objectHashes") or {}
        hit={hd for hd,hh in hashes.items() if hh in targets}
        if not hit: continue
        ev=[]
        for (pg,) in con.execute("select payload_gz from v3_timeline_chunks where operation_id=? order by chunk_index",(oid,)):
            try: ev.extend(orjson.loads(d.decompress(pg)))
            except Exception: pass
        dv={o["handle"] for e in ev if e.get("type")=="transform" for o in (e.get("value") or {}).get("outputs",[]) if o.get("kind")=="frame"}
        for hd in hit:
            ops.add(oid)
            if hd in dv: derived+=1
            else: root+=1
    print("   operations touched:",len(ops)," root handles:",root," derived handles:",derived)
    con.close()
