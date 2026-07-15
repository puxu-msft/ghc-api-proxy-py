import re
from collections.abc import Mapping, Set

MODEL_PREFERENCE = {
    "opus": (
        "claude-opus-4.6",
        "claude-opus-4.5",
        "claude-opus-4.1",
        "claude-opus-4",
    ),
    "sonnet": (
        "claude-sonnet-4.6",
        "claude-sonnet-4.5",
        "claude-sonnet-4",
    ),
    "haiku": ("claude-haiku-4.5",),
}
VERSION_PATTERN = re.compile(
    r"^(claude-(?P<family>opus|sonnet|haiku)-(?P<major>\d+))-(?P<minor>\d+)(?P<suffix>(?:-.+)?)$",
    re.IGNORECASE,
)
DATE_SUFFIX = re.compile(r"-(?:19|20)\d{6}$")
BRACKET_SUFFIX = re.compile(r"^(?P<base>.+)\[(?P<suffix>[^\]]+)\]$")


class ModelResolutionError(ValueError):
    pass


def normalize_for_matching(model_id: str) -> str:
    return model_id.lower().replace(".", "-")


def _normalize_version(model_id: str) -> str:
    match = VERSION_PATTERN.match(model_id)
    if match is None:
        return model_id
    return (
        f"claude-{match.group('family').lower()}-"
        f"{match.group('major')}.{match.group('minor')}{match.group('suffix')}"
    )


def _family(model_id: str) -> str | None:
    normalized = normalize_for_matching(model_id)
    for family in MODEL_PREFERENCE:
        if normalized == family or normalized.startswith(f"claude-{family}-"):
            return family
    return None


class ModelResolver:
    def __init__(
        self,
        *,
        available_ids: Set[str],
        model_overrides: Mapping[str, str],
        model_mappings: Mapping[str, str] | None = None,
    ) -> None:
        self._available = frozenset(available_ids)
        self._overrides = dict(model_overrides)
        self._mappings = dict(model_mappings or {})

    def resolve(self, raw_name: str) -> str:
        bracket = BRACKET_SUFFIX.match(raw_name)
        if bracket is not None:
            base = self._resolve(bracket.group("base"), set(), apply_family_override=True)
            candidate = f"{base}-{bracket.group('suffix')}"
            return candidate
        for family in MODEL_PREFERENCE:
            prefix = f"{family}-"
            if raw_name.startswith(prefix):
                base = self._resolve(family, set(), apply_family_override=True)
                candidate = f"{base}-{raw_name[len(prefix):]}"
                return candidate
        return self._resolve(raw_name, set(), apply_family_override=True)

    def _resolve(
        self,
        name: str,
        visited: set[str],
        *,
        apply_family_override: bool,
    ) -> str:
        if name in visited:
            raise ModelResolutionError(f"model override cycle detected at {name!r}")
        visited.add(name)

        exact_target = self._overrides.get(name)
        if exact_target is None:
            exact_target = self._mappings.get(name)
        if exact_target is not None:
            return self._resolve(exact_target, visited, apply_family_override=False)

        without_date = DATE_SUFFIX.sub("", name)
        normalized = _normalize_version(without_date)

        normalized_target = self._overrides.get(normalized)
        if normalized_target is None:
            normalized_target = self._mappings.get(normalized)
        if normalized_target is not None:
            return self._resolve(normalized_target, visited, apply_family_override=False)

        family = _family(normalized)
        if apply_family_override and family is not None and family in self._overrides:
            return self._resolve(self._overrides[family], visited, apply_family_override=False)

        if normalized in self._available:
            return normalized

        if family is not None:
            suffix = ""
            version_match = VERSION_PATTERN.match(without_date)
            if version_match is not None:
                suffix = version_match.group("suffix").removeprefix("-")
                if suffix:
                    return normalized
            elif normalized.startswith(f"{family}-"):
                suffix = normalized[len(family) + 1 :]
            for preferred in MODEL_PREFERENCE[family]:
                candidate = f"{preferred}-{suffix}" if suffix else preferred
                if candidate in self._available:
                    return candidate

        return normalized