"""Structural scan of ROOT (upstream-sent) frames only, per operation."""
import sqlite3, sys, json
from collections import Counter, defaultdict
import orjson, zstandard

def main(path, out, limit_ops=None):
    d = zstandard.ZstdDecompressor()
    con = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
    ops = [r[0] for r in con.execute("select operation_id from v3_operations order by created_at")]
    if limit_ops: ops = ops[:limit_ops]
    ev = Counter()            # root frame event/type
    statuses = Counter()      # response.status on terminal frames
    incdet = Counter()        # json of incomplete_details when non-null
    errs = Counter()          # response.error / error frame payloads
    stopreasons = Counter()   # anthropic message_delta stop_reason on ROOT frames
    finish = Counter()
    itemstatus = Counter()
    refusals = Counter()
    samples = defaultdict(list)
    nops = 0; nframes = 0
    for oid in ops:
        row = con.execute("select manifest_gz from v3_operations where operation_id=?", (oid,)).fetchone()
        if not row: continue
        try:
            manifest = orjson.loads(d.decompress(row[0]))
        except Exception: continue
        hashes = manifest.get("objectHashes") or {}
        events = []
        for (pg,) in con.execute("select payload_gz from v3_timeline_chunks where operation_id=? order by chunk_index",(oid,)):
            try: events.extend(orjson.loads(d.decompress(pg)))
            except Exception: pass
        if not events: continue
        derived = {o["handle"] for e in events if e.get("type")=="transform"
                   for o in (e.get("value") or {}).get("outputs",[]) if o.get("kind")=="frame"}
        roots = [e for e in events if e.get("type")=="frame" and e.get("handle") not in derived]
        if not roots: continue
        nops += 1
        for e in roots:
            h = hashes.get(str(e.get("handle","")))
            if not h: continue
            r = con.execute("select canonical_gz from v3_objects where hash=?", (h,)).fetchone()
            if not r: continue
            try: frame = orjson.loads(d.decompress(r[0]))
            except Exception: continue
            nframes += 1
            if frame.get("synthetic"):
                ev[f"SYNTHETIC:{frame.get('event') or frame.get('type')}"] += 1
                continue
            raw = frame.get("data")
            if not isinstance(raw, str): continue
            try: p = orjson.loads(raw)
            except Exception: continue
            t = str(frame.get("event") or p.get("type") or "?")
            ev[t] += 1
            resp = p.get("response") if isinstance(p.get("response"), dict) else None
            if resp is not None:
                statuses[(t, str(resp.get("status")))] += 1
                idet = resp.get("incomplete_details")
                if idet:
                    key = json.dumps(idet, sort_keys=True)
                    incdet[key] += 1
                    if len(samples[("incdet",key)])<2:
                        samples[("incdet",key)].append((path,oid,t,json.dumps({k:v for k,v in resp.items() if k in ("status","incomplete_details","error","usage","id")})[:800]))
                rerr = resp.get("error")
                if rerr:
                    key = json.dumps(rerr, sort_keys=True)[:300]
                    errs[("response.error",key)] += 1
                    if len(samples[("err",key)])<2:
                        samples[("err",key)].append((path,oid,t,json.dumps(rerr)[:800]))
            if t == "error" or p.get("type")=="error":
                key = json.dumps(p, sort_keys=True)[:300]
                errs[("frame:error",key)] += 1
                if len(samples[("err2",key)])<2:
                    samples[("err2",key)].append((path,oid,t,json.dumps(p)[:800]))
            if t == "message_delta":
                dl = p.get("delta") or {}
                stopreasons[str(dl.get("stop_reason"))] += 1
            if "finish_reason" in raw:
                for ch in (p.get("choices") or []):
                    if isinstance(ch, dict) and ch.get("finish_reason") is not None:
                        finish[str(ch.get("finish_reason"))] += 1
            it = p.get("item")
            if isinstance(it, dict):
                itemstatus[(str(it.get("type")), str(it.get("status")))] += 1
                if "refusal" in it and it.get("refusal"):
                    refusals[str(it.get("refusal"))[:200]] += 1
            if p.get("part") and isinstance(p["part"], dict) and p["part"].get("type")=="refusal":
                refusals["part:refusal"] += 1
    with open(out,"w") as f:
        f.write(f"db={path} ops_with_roots={nops} root_frames={nframes}\n\nROOT FRAME EVENT TYPES\n")
        for k,c in ev.most_common(100): f.write(f"  {k}: {c}\n")
        f.write("\nresponse.status by terminal event\n")
        for k,c in statuses.most_common(50): f.write(f"  {k}: {c}\n")
        f.write("\nNON-NULL incomplete_details\n")
        for k,c in incdet.most_common(50): f.write(f"  {k}: {c}\n")
        f.write("\nERRORS\n")
        for k,c in errs.most_common(60): f.write(f"  {k}: {c}\n")
        f.write("\nmessage_delta.stop_reason (root frames)\n")
        for k,c in stopreasons.most_common(30): f.write(f"  {k}: {c}\n")
        f.write("\nchoices[].finish_reason\n")
        for k,c in finish.most_common(30): f.write(f"  {k}: {c}\n")
        f.write("\noutput item (type,status)\n")
        for k,c in itemstatus.most_common(40): f.write(f"  {k}: {c}\n")
        f.write("\nrefusals\n")
        for k,c in refusals.most_common(20): f.write(f"  {k}: {c}\n")
        f.write("\nSAMPLES\n")
        for k,v in samples.items():
            for s in v: f.write(f"  {k[0]} :: {s}\n")
    print("done", path, nops, nframes)

main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv)>3 else None)
