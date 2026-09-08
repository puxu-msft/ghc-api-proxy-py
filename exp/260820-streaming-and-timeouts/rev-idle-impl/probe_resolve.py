from app.pipeline.timeouts import resolve_timeout as R

cases = [
    ("doc: literal beats glob", "gpt-5.6-terra", 300, {"gpt-*": 90, "terra": 45}, 45),
    ("doc: glob beats *", "gpt-5.6-terra", 300, {"*": 30, "gpt-*": 90}, 90),
    ("doc: literal beats *", "gpt-5.6-terra", 300, {"*": 30, "terra": 45}, 45),
    ("doc: longest literal", "claude-opus-5", 300, {"opus": 60, "claude-opus": 75}, 75),
    ("doc: longest glob", "gpt-5.6-terra", 300, {"gpt-*": 90, "gpt-5.6-*": 120}, 120),
    ("doc: override 0 disables", "claude-opus-5", 300, {"opus": 0}, 0),
    ("doc: * override 0 disables", "anything", 300, {"*": 0}, 0),
    ("doc: no match -> scalar", "claude-opus-5", 300, {"gpt": 60}, 300),
    ("SHORT literal vs LONG glob", "gpt-5.6-terra", 300, {"gpt": 60, "gpt-5.6-terr?": 120}, 60),
    ("negative override passes through", "claude-opus-5", 300, {"opus": -5}, -5),
    ("bracket key treated as glob", "gpt-5", 300, {"gpt-[0-9]": 90}, 90),
    ("bracket key literal-ish", "a[b]c", 300, {"[b]": 77}, "??"),
    ("empty-string key", "anything", 300, {"": 42}, 42),
    ("tie: same class same len", "gpt-5-terra", 300, {"terra": 45, "gpt-5": 99}, "order?"),
    ("tie reversed", "gpt-5-terra", 300, {"gpt-5": 99, "terra": 45}, "order?"),
]
for name, model, scalar, ov, expect in cases:
    got = R(model, scalar, ov)
    flag = "" if expect in ("??", "order?") else ("  OK" if got == expect else f"  MISMATCH expected={expect}")
    print(f"{name:36s} model={model!r:16s} ov={ov} -> {got}{flag}")
