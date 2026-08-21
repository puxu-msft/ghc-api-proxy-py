import sqlite3, sys
from datetime import datetime, timezone
import orjson, zstandard
d=zstandard.ZstdDecompressor()
for p in sys.argv[1:]:
    con=sqlite3.connect(f"file:{p}?immutable=1",uri=True)
    zero=0; nonzero=0; first_nonzero=None; last_zero=None
    for (oid,created) in con.execute("select operation_id, created_at from v3_operations order by created_at"):
        ev=[]
        for (pg,) in con.execute("select payload_gz from v3_timeline_chunks where operation_id=? order by chunk_index",(oid,)):
            try: ev.extend(orjson.loads(d.decompress(pg)))
            except Exception: pass
        has_frame=any(e.get("type")=="frame" for e in ev)
        if not has_frame: continue
        nt=sum(1 for e in ev if e.get("type")=="transform")
        if nt==0:
            zero+=1; last_zero=(oid,created)
        else:
            nonzero+=1
            if first_nonzero is None: first_nonzero=(oid,created)
    def ts(x): return datetime.fromtimestamp(x/1000,timezone.utc).strftime("%Y-%m-%d %H:%M") if x else "?"
    print(p.split("/")[-1], "ops with frames: no-transform", zero, "with-transform", nonzero,
          "| last no-transform", (last_zero[0], ts(last_zero[1])) if last_zero else None,
          "| first with-transform", (first_nonzero[0], ts(first_nonzero[1])) if first_nonzero else None)
    con.close()
