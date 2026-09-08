import importlib, json, sys
importlib.import_module(sys.argv[1])
print(json.dumps(sorted(n for n in sys.modules if n.startswith("app."))))
