"""Check every row of the r4 capability table against the frozen algorithm.

Algorithm: `i` is the 0-based ordinal among ALL reasoning items of the turn (bare markers
included). On the way back, number the recovered reasoning blocks 0,1,2... in source order and
require every payload carrier's `i` to equal its own ordinal. Bare markers occupy an ordinal but
carry no `i`, so they are skipped by the comparison.
"""
BARE = None  # a bare marker: occupies a slot, carries no i

def detects(blocks) -> bool:
    """True if the anomaly is caught."""
    return any(i is not None and i != pos for pos, i in enumerate(blocks))

def emit(n_items, bare_at=()):
    """What the producer sends for a turn of n_items reasoning items."""
    return [BARE if k in bare_at else k for k in range(n_items)]

rows = [
    ("reorder",                    [1, 0],                       True),
    ("duplicate",                  [0, 0],                       True),
    ("prefix loss",                [1, 2],                       True),
    ("interior payload loss",      [0, 2],                       True),
    ("interior BARE loss",         [0, 2],                       True),   # from [0,BARE,2]
    ("legal interior bare",        [0, BARE, 2],                 False),  # must NOT false-positive
    ("legal all-payload",          [0, 1, 2],                    False),
    ("legal leading bare",         [BARE, 1],                    False),
    ("trailing loss (2 of 3)",     [0],                          False),  # from [0,1,2]
    ("trailing bare loss",         [0],                          False),  # from [0,BARE]
]
print(f"{'case':26} {'claimed':>8} {'actual':>8}  ok")
ok = True
for name, blocks, claimed in rows:
    actual = detects(blocks)
    good = actual == claimed
    ok &= good
    print(f"{name:26} {str(claimed):>8} {str(actual):>8}  {'OK' if good else '*** MISMATCH'}")
print()
print("emit sanity: 3 items with bare at 1 ->", emit(3, bare_at={1}))
print("VERDICT:", "table matches the algorithm" if ok else "TABLE IS WRONG")
