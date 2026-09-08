"""Rename httpx/httpcore imports and attribute access to httpx2/httpcore2 — code tokens only.

Comments and strings are left alone on purpose. Roughly fifty of this repo's mentions of `httpx` sit in prose, and a good number of those are dated statements about how httpx 0.28.1 or httpcore 1.0.9 actually behaved. Renaming those would turn a measured fact into a false one.
They get a separate, reviewed pass.

Usage:
    python rename_imports.py --check <paths...>   # report what would change, touch nothing
    python rename_imports.py --write <paths...>
"""

from __future__ import annotations

import argparse
import io
import sys
import tokenize
from pathlib import Path

RENAMES = {"httpx": "httpx2", "httpcore": "httpcore2"}


def rewrite(source: str) -> tuple[str, int]:
    """Return the rewritten source and how many NAME tokens were renamed."""
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    replacements: list[tuple[int, int, int, str]] = []  # row, col_start, col_end, new text
    changed = 0

    for index, token in enumerate(tokens):
        if token.type != tokenize.NAME or token.string not in RENAMES:
            continue
        # Attribute position, not a module reference: `opentelemetry.instrumentation.httpx` is somebody else's submodule and keeps its name even after we stop using the package it wraps.
        previous = tokens[index - 1] if index else None
        if previous is not None and previous.type == tokenize.OP and previous.string == ".":
            continue
        # `import httpx` / `import httpcore`: rename and let the module keep its own name, since every use site is rewritten too. `from httpx._utils import ...` and `from httpcore import ...` are the same shape. An `as` alias would need care, but this repo has none — asserted below.
        following = tokens[index + 1] if index + 1 < len(tokens) else None
        if following is not None and following.type == tokenize.NAME and following.string == "as":
            raise SystemExit(f"aliased import of {token.string!r} at line {token.start[0]}; handle by hand")
        replacements.append((token.start[0], token.start[1], token.end[1], RENAMES[token.string]))
        changed += 1

    if not changed:
        return source, 0

    lines = source.splitlines(keepends=True)
    # Apply right-to-left within each line so earlier columns stay valid.
    for row, col_start, col_end, new_text in sorted(replacements, reverse=True):
        line = lines[row - 1]
        lines[row - 1] = line[:col_start] + new_text + line[col_end:]
    return "".join(lines), changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()

    total_files = 0
    total_tokens = 0
    for root in args.paths:
        for path in sorted(Path(root).rglob("*.py")):
            source = path.read_text()
            try:
                rewritten, changed = rewrite(source)
            except SystemExit:
                raise
            except tokenize.TokenError as error:
                print(f"SKIP (unparseable) {path}: {error}", file=sys.stderr)
                continue
            if not changed:
                continue
            total_files += 1
            total_tokens += changed
            print(f"{'rewrote' if args.write else 'would rewrite'} {path}: {changed} tokens")
            if args.write:
                path.write_text(rewritten)

    print(f"\n{total_files} files, {total_tokens} tokens")
    return 0


if __name__ == "__main__":
    sys.exit(main())
