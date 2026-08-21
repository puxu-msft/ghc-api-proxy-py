import sqlite3, glob, os, sys, gzip
from collections import Counter
import zstandard
PATS=[b"prompt token count", b"prompt is too long", b"context_length_exceeded", b"model_context_window_exceeded",
      b"content_filter", b"off_topic", b"maximum context length", b"exceeds the limit of", b"too many tokens",
      b"context window", b"incomplete_details"]
d=zstandard.ZstdDecompressor()
for p in sorted(glob.glob(os.path.expanduser("~/.local/share/copilot-api/history-v3*.db"))):
    con=sqlite3.connect(f"file:{p}?immutable=1",uri=True)
    hits=Counter(); samples={}
    try:
        n=0
        for enc, blob in con.execute("select encoding, evidence_gz from v3_transport_evidence"):
            n+=1
            try: b=d.decompress(blob)
            except Exception:
                try: b=gzip.decompress(blob)
                except Exception: continue
            for pat in PATS:
                if pat in b:
                    hits[pat]+=1
                    if pat not in samples:
                        i=b.find(pat); samples[pat]=b[max(0,i-400):i+400]
        print("==",os.path.basename(p),"evidence rows",n,dict((k.decode(),v) for k,v in hits.items()))
        for k,v in samples.items():
            print("   ---",k.decode()); print("   ",v.decode("utf8","replace")[:700].replace("\n"," "))
    except sqlite3.DatabaseError as e:
        print("==",os.path.basename(p),"ERR",e)
    con.close()
