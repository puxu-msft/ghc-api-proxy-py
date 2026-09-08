"""List or filter hunks of `git diff` for one file."""
import re, subprocess, sys

def hunks(path):
    d = subprocess.run(["git", "diff", "--", path], capture_output=True, text=True, check=True).stdout
    lines = d.splitlines(keepends=True)
    head_end = next(i for i, l in enumerate(lines) if l.startswith("@@"))
    header, body, cur = lines[:head_end], [], None
    for l in lines[head_end:]:
        if l.startswith("@@"):
            cur = [l]; body.append(cur)
        else:
            cur.append(l)
    return header, body

if __name__ == "__main__":
    path = sys.argv[1]
    header, body = hunks(path)
    if len(sys.argv) == 2:
        for i, h in enumerate(body):
            added = [l[1:].strip()[:90] for l in h[1:] if l.startswith("+")][:2]
            print(f"[{i}] {h[0].strip()[:70]}")
            for a in added:
                print(f"      + {a}")
    else:
        keep = {int(x) for x in sys.argv[2].split(",")}
        out = "".join(header) + "".join("".join(body[i]) for i in sorted(keep))
        sys.stdout.write(out)
