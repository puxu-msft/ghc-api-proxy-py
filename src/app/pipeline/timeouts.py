"""Resolving the per-model timeout overrides.

The spec keys overrides by model-name substring or glob, and fixes the precedence.
A literal substring beats a glob, a glob beats `*`, and within one class the longest key wins.

Determinism is the point. A request must not get a different timeout depending on dict order.
"""

from collections.abc import Mapping
from enum import IntEnum
from fnmatch import fnmatchcase

WILDCARD = "*"
GLOB_CHARS = ("*", "?", "[")


class Specificity(IntEnum):
    """Higher wins. Ordered as the spec states."""

    WILDCARD = 0
    GLOB = 1
    LITERAL = 2


def _classify(key: str) -> Specificity:
    if key == WILDCARD:
        return Specificity.WILDCARD
    if any(char in key for char in GLOB_CHARS):
        return Specificity.GLOB
    return Specificity.LITERAL


def _matches(key: str, model: str) -> bool:
    if key == WILDCARD:
        return True
    if _classify(key) is Specificity.GLOB:
        return fnmatchcase(model, key)
    return key in model


def resolve_timeout(
    model: str,
    scalar: int,
    overrides: Mapping[str, int],
) -> int:
    """Pick the timeout for one model.

    A matching override wins over the scalar, including when it is 0.
    The spec uses 0 to disable, so an override of 0 is a decision, not an absent value.
    """
    best_key: str | None = None
    best_rank: tuple[int, int] = (-1, -1)
    for key in overrides:
        if not _matches(key, model):
            continue
        rank = (int(_classify(key)), len(key))
        if rank > best_rank:
            best_rank = rank
            best_key = key
    if best_key is None:
        return scalar
    return overrides[best_key]
