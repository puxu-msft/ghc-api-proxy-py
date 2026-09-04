import importlib, json, sys
mods = {}
for entry in ("app.cli", "app.server.app_factory"):
    importlib.import_module(entry)
    mods[entry] = sorted(n for n in sys.modules if n.startswith("app."))
    for n in list(sys.modules):
        if n.startswith("app."): del sys.modules[n]
print(json.dumps(mods))
