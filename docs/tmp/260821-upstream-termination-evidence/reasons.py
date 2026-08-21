import sqlite3, sys, re
from collections import Counter
import zstandard
IDET = re.compile(rb'\\?"incomplete_details\\?"\s*:\s*\{[^}]*\\?"reason\\?"\s*:\s*\\?"([a-z_]+)')
REFU = re.compile(rb'\\?"type\\?"\s*:\s*\\?"refusal\\?"')
CF   = re.compile(rb'\\?"reason\\?"\s*:\s*\\?"(content_filter|safety|policy|context[a-z_]*)\\?"')
d=zstandard.ZstdDecompressor()
for path in sys.argv[1:]:
    con=sqlite3.connect(f"file:{path}?immutable=1",uri=True)
    reasons=Counter(); refusals=0; cf=Counter(); n=0
    cur=con.execute("select canonical_gz from v3_objects where kind='frame'")
    while True:
        rows=cur.fetchmany(5000)
        if not rows: break
        for (blob,) in rows:
            try: b=d.decompress(blob)
            except Exception: continue
            n+=1
            for m in IDET.finditer(b): reasons[m.group(1)]+=1
            if REFU.search(b): refusals+=1
            for m in CF.finditer(b): cf[m.group(1)]+=1
    print(path, "frames", n)
    print("   non-null incomplete_details reasons:", {k.decode():v for k,v in reasons.items()})
    print("   frames containing a refusal-typed part:", refusals)
    print("   any reason == content_filter/safety/policy/context*:", {k.decode():v for k,v in cf.items()})
    con.close()
