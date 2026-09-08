import pathlib
import shutil

# Literal paths, one per line, so the target set is readable without running this.
TARGETS = [
    pathlib.Path("/home/xp/src/ghc-api-proxy-py/src/app/context"),
    pathlib.Path("/home/xp/src/ghc-api-proxy-py/src/app/delivery"),
    pathlib.Path("/home/xp/src/ghc-api-proxy-py/src/app/history"),
    pathlib.Path("/home/xp/src/ghc-api-proxy-py/src/app/hooks"),
    pathlib.Path("/home/xp/src/ghc-api-proxy-py/src/app/openai"),
    pathlib.Path("/home/xp/src/ghc-api-proxy-py/src/app/routes"),
]

for directory in TARGETS:
    if not directory.exists():
        print(f"  {directory}: absent, skipped")
        continue
    real = [p for p in directory.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    assert not real, f"refusing to delete {directory}: it still holds {real}"
    shutil.rmtree(directory)
    print(f"  removed {directory}")
