"""Stage this migration's changes without taking a peer's uncommitted work along.

Five files in the shared worktree carry both the mechanical httpx→httpx2 rename and edits from
another session that are still uncommitted. For those, what gets committed is HEAD's blob with the
rename applied and nothing else, so the peer's edits stay in the worktree and land in their own
commit later. Every other changed file is committed from the worktree as it stands.

Classification is mechanical, not a guess: a file counts as ours alone when renaming HEAD's blob
reproduces the worktree byte for byte.

Usage:
    python stage_migration.py --check
    python stage_migration.py --write   # writes into GIT_INDEX_FILE, which must be set
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rename_imports import rewrite  # noqa: E402

REPO = "/home/xp/src/ghc-api-proxy-py"


def git(*args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", REPO, *args], check=True, stdout=subprocess.PIPE
    )
    return result.stdout if binary else result.stdout.decode()


def changed_paths() -> list[str]:
    names = git("diff", "--name-only", "HEAD", "--", "src", "tests", "pyproject.toml", "uv.lock")
    assert isinstance(names, str)
    return [line for line in names.splitlines() if line]


def head_blob(path: str) -> bytes | None:
    try:
        return subprocess.run(
            ["git", "-C", REPO, "show", f"HEAD:{path}"], check=True, stdout=subprocess.PIPE
        ).stdout
    except subprocess.CalledProcessError:
        return None  # new file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    ours: list[str] = []
    mixed: list[str] = []

    for path in changed_paths():
        worktree = (Path(REPO) / path).read_bytes()
        base = head_blob(path)
        if base is None or not path.endswith(".py"):
            ours.append(path)
            continue
        try:
            renamed, _ = rewrite(base.decode())
        except Exception:
            ours.append(path)
            continue
        (ours if renamed.encode() == worktree else mixed).append(path)

    print(f"ours alone ({len(ours)}), committed from the worktree")
    print(f"mixed with a peer's edits ({len(mixed)}), committed as rename-only:")
    for path in mixed:
        print(f"  {path}")

    if not args.write:
        return 0

    import os

    if not os.environ.get("GIT_INDEX_FILE"):
        raise SystemExit("refusing to write: GIT_INDEX_FILE is not set, that would touch the shared index")

    for path in ours:
        git("update-index", "--add", "--", path)
    for path in mixed:
        base = head_blob(path)
        assert base is not None
        renamed, _ = rewrite(base.decode())
        blob = subprocess.run(
            ["git", "-C", REPO, "hash-object", "-w", "--stdin"],
            check=True,
            input=renamed.encode(),
            stdout=subprocess.PIPE,
        ).stdout.decode().strip()
        mode = git("ls-tree", "HEAD", "--", path).split()[0]
        git("update-index", "--add", "--cacheinfo", f"{mode},{blob},{path}")
    print(f"\nstaged {len(ours) + len(mixed)} paths into {os.environ['GIT_INDEX_FILE']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
