import sqlite3, json
import orjson, zstandard
d=zstandard.ZstdDecompressor()
p="/home/xp/.local/share/copilot-api/history-v3-260807.db"
con=sqlite3.connect(f"file:{p}?immutable=1",uri=True)
for oid in ("req_1784308734092_205","req_1784308747894_207"):
    row=con.execute("select manifest_gz from v3_operations where operation_id=?",(oid,)).fetchone()
    man=orjson.loads(d.decompress(row[0])); hashes=man.get("objectHashes") or {}
    ev=[]
    for (pg,) in con.execute("select payload_gz from v3_timeline_chunks where operation_id=? order by chunk_index",(oid,)):
        ev.extend(orjson.loads(d.decompress(pg)))
    derived={o["handle"] for e in ev if e.get("type")=="transform" for o in (e.get("value") or {}).get("outputs",[]) if o.get("kind")=="frame"}
    print("==",oid,"timeline events",len(ev),"derived frame handles",len(derived))
    for e in ev:
        if e.get("type")!="frame": continue
        h=hashes.get(str(e.get("handle","")))
        if not h: continue
        r=con.execute("select canonical_gz from v3_objects where hash=?",(h,)).fetchone()
        if not r: continue
        fr=orjson.loads(d.decompress(r[0]))
        print("   handle",e["handle"],"seq",e["sequence"],"root",e["handle"] not in derived,
              "type",fr.get("type"),"event",fr.get("event"),"synthetic",fr.get("synthetic"))
    print("   transforms:", [(e.get("value") or {}).get("transformId") for e in ev if e.get("type")=="transform"])
