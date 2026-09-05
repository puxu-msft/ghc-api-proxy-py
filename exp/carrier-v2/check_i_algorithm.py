"""Check the superseded ordinal-only v2 candidate against its historical table.

This is not the current v2 algorithm or an acceptance oracle. The 2026-09-04 living Spec at
`.dev/docs/reasoning-carrier/spec.md` removed ordinal `i` from this producer in favour of a typed
record envelope. The old algorithm is retained only to reproduce the capability boundary that
caused the candidate to be rejected.
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
    # Found by review, not by me: the detector only ever compares payload carriers, so any
    # corruption confined to bare markers is invisible wherever it sits — not just at the tail.
    # The ten rows above were all cases I thought of, which is exactly why they could not
    # support the general claim I drew from them.
    ("bare-only swap (interior)",  [BARE, BARE, 2],              False),  # [bareA,bareB,p2] <-> swapped
    ("bare-only substitution",     [BARE, BARE, 2],              False),  # one bare duplicated over another
]
print(f"{'case':26} {'claimed':>8} {'actual':>8}  ok")
ok = True
for name, blocks, claimed in rows:
    actual = detects(blocks)
    good = actual == claimed
    ok &= good
    print(f"{name:26} {claimed!s:>8} {actual!s:>8}  {'OK' if good else '*** MISMATCH'}")
print()
print("emit sanity: 3 items with bare at 1 ->", emit(3, bare_at={1}))
print(
    "HISTORICAL VERDICT:",
    "superseded table matches its old algorithm" if ok else "SUPERSEDED TABLE IS WRONG",
)
