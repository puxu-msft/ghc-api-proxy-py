import importlib, pathlib, subprocess, sys
files = [f for f in subprocess.run(["git","ls-files","src/app"],capture_output=True,text=True).stdout.split() if f.endswith(".py")]
bad = []
for f in files:
    mod = f[len("src/"):-3].replace("/", ".")
    if mod.endswith(".__init__"): mod = mod[:-len(".__init__")]
    if mod == "app.__main__": continue          # 入口自身，import 会执行它
    try:
        importlib.import_module(mod)
    except Exception as exc:
        bad.append((mod, type(exc).__name__, str(exc)[:70]))
print(f"  检查了 {len(files)} 个模块，import 失败 {len(bad)} 个：")
for m, k, e in bad: print(f"    {m:44s} {k}: {e}")
