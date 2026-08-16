"""Model name resolution, per the rules in `config.example.yaml`.

`model_mappings` is the sole source; there are no built-in defaults.

The spec's compatibility rules are matching rules, not rewriting rules.
They decide which mapping key an inbound name hits.
The date suffix is deliberately not among them; since 2026/07/16 it must be configured.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

BRACKET_SUFFIX = re.compile(r"^(?P<base>.+)\[(?P<suffix>[^\]]+)\]$")
_MAX_ALIAS_HOPS = 8


@dataclass(frozen=True, slots=True)
class ModelResolution:
    requested: str
    resolved: str
    matched_key: str = ""
    passthrough: bool = False
    hops: int = 0


def canonical(name: str) -> str:
    """Fold the spellings the spec calls equivalent.

    Case is insensitive and `.` and `-` are interchangeable.
    `claude-opus-4-5` and `claude-opus-4.5` are therefore the same key.
    """
    return name.strip().lower().replace(".", "-")


def candidate_keys(name: str) -> tuple[str, ...]:
    """The keys an inbound name may hit, in the order the spec tries them.

    `opus[1m]` tries `opus-1m` before `opus`, so a bracket-specific mapping wins over the base one.
    """
    stripped = name.strip()
    candidates = [stripped]
    bracket = BRACKET_SUFFIX.match(stripped)
    if bracket is not None:
        base = bracket.group("base")
        candidates.append(f"{base}-{bracket.group('suffix')}")
        candidates.append(base)

    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        key = canonical(candidate)
        if key and key not in seen:
            seen.add(key)
            ordered.append(key)
    return tuple(ordered)


def _index(mappings: Mapping[str, str]) -> dict[str, tuple[str, str]]:
    """Index mappings by canonical key, keeping the original key for reporting."""
    return {canonical(key): (key, value) for key, value in mappings.items()}


def resolve_model(
    requested: str,
    *,
    mappings: Mapping[str, str],
    available: frozenset[str],
) -> ModelResolution:
    """Resolve an inbound model name against the configured mappings.

    A target already on offer resolves directly.
    Otherwise it is treated as an alias and resolved again.
    If it is still unavailable the mapping is abandoned and the original name passes through.
    """
    index = _index(mappings)
    available_index = {canonical(model): model for model in available}

    current = requested
    matched_key = ""
    for hop in range(_MAX_ALIAS_HOPS):
        direct = available_index.get(canonical(current))
        if direct is not None and hop > 0:
            return ModelResolution(requested, direct, matched_key, hops=hop)

        entry = next(
            (index[key] for key in candidate_keys(current) if key in index),
            None,
        )
        if entry is None:
            break
        matched_key, current = entry

        target = available_index.get(canonical(current))
        if target is not None:
            return ModelResolution(requested, target, matched_key, hops=hop + 1)

    if matched_key:
        # A mapping matched but its target never became available; the spec says pass through.
        return ModelResolution(requested, requested.strip(), matched_key, passthrough=True)

    direct = available_index.get(canonical(requested))
    if direct is not None:
        return ModelResolution(requested, direct)
    return ModelResolution(requested, requested.strip(), passthrough=True)
