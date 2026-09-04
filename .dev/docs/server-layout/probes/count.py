import json, sys
m = json.load(sys.stdin)
pipe = sorted(x for x in m if x.startswith("app.pipeline"))
deliv = [x for x in pipe if x.startswith("app.pipeline.delivery")]
print(f"  total app.* = {len(m)} | app.pipeline.* = {len(pipe)} | app.pipeline.delivery.* = {len(deliv)}")
print(f"  app.observability reachable = {'app.observability' in m}")
