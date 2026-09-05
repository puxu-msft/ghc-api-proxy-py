"""Holds the configuration snapshot in effect and swaps it on reload.

`current` always describes what the process is actually using, never what a file declares.
Paths the spec marks as needing a restart are pinned to their startup values on reload.
They are reported instead of silently applied.
"""

from collections.abc import Callable, Iterator
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast

from app.config.schema import NOT_HOT_RELOADABLE, PROVIDER_NOT_HOT_RELOADABLE, ProxyConfig


@dataclass(frozen=True, slots=True)
class ReloadOutcome:
    config: ProxyConfig
    changed: bool
    # Paths whose new value was discarded because the spec marks them restart-only.
    restart_required: tuple[str, ...]


def _expand(pattern: str, values: dict[str, Any]) -> Iterator[tuple[str, ...]]:
    """Expand one dotted pattern into concrete paths, resolving `*` against the current keys."""
    paths: list[tuple[str, ...]] = [()]
    cursor_sets: list[dict[str, Any]] = [values]
    for segment in pattern.split("."):
        next_paths: list[tuple[str, ...]] = []
        next_cursors: list[dict[str, Any]] = []
        for path, cursor in zip(paths, cursor_sets, strict=True):
            if segment == "*":
                keys = list(cursor)
            elif segment in cursor:
                keys = [segment]
            else:
                keys = []
            for key in keys:
                child = cursor[key]
                next_paths.append((*path, key))
                next_cursors.append(cast(dict[str, Any], child) if isinstance(child, dict) else {})
        paths, cursor_sets = next_paths, next_cursors
    yield from paths


def _read(values: dict[str, Any], path: tuple[str, ...]) -> Any:
    cursor: Any = values
    for key in path:
        if not isinstance(cursor, dict) or key not in cursor:
            return None
        cursor = cast(dict[str, Any], cursor)[key]
    return cursor


def _write(values: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cursor = values
    for key in path[:-1]:
        child = cursor.get(key)
        if not isinstance(child, dict):
            child = {}
            cursor[key] = child
        cursor = cast(dict[str, Any], child)
    cursor[path[-1]] = value


def _providers(values: dict[str, Any]) -> dict[str, Any]:
    raw = values.get("model_providers")
    if not isinstance(raw, dict):
        return {}
    return cast(dict[str, Any], raw)


def _provider_type(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    candidate = cast(dict[str, Any], value).get("type")
    return candidate if isinstance(candidate, str) else ""


def _pin_provider_graph(
    startup_values: dict[str, Any],
    candidate_values: dict[str, Any],
    pinned: set[str],
) -> bool:
    """Keep provider membership and variants aligned with the instances built at startup."""
    startup_providers = _providers(startup_values)
    candidate_providers = _providers(candidate_values)
    changed = False
    for name in sorted(set(startup_providers) | set(candidate_providers)):
        was = startup_providers.get(name)
        now = candidate_providers.get(name)
        if was is not None and now is not None and _provider_type(was) == _provider_type(now):
            continue
        changed = True
        if was is None:
            candidate_providers.pop(name, None)
        else:
            candidate_providers[name] = deepcopy(was)
        pinned.add(f"model_providers.{name}")
    return changed


_PROVIDER_GRAPH_SELECTORS: tuple[tuple[str, ...], ...] = (
    ("default_model_provider",),
    ("fallback_model_provider",),
    ("inbound", "anthropic_count_tokens", "providers"),
)


def _pin_provider_graph_selectors(
    startup_values: dict[str, Any],
    candidate_values: dict[str, Any],
    pinned: set[str],
) -> None:
    for path in _PROVIDER_GRAPH_SELECTORS:
        was = _read(startup_values, path)
        now = _read(candidate_values, path)
        _write(candidate_values, path, deepcopy(was))
        if was != now:
            pinned.add(".".join(path))


def _pin_type_scoped_provider_fields(
    startup_values: dict[str, Any],
    candidate_values: dict[str, Any],
    pinned: set[str],
) -> None:
    startup_providers = _providers(startup_values)
    candidate_providers = _providers(candidate_values)
    for name in sorted(set(startup_providers) & set(candidate_providers)):
        provider_type = _provider_type(startup_providers[name])
        for field in PROVIDER_NOT_HOT_RELOADABLE.get(provider_type, ()):
            path = ("model_providers", name, field)
            was = _read(startup_values, path)
            now = _read(candidate_values, path)
            if was != now:
                _write(candidate_values, path, was)
                pinned.add(".".join(path))


def pin_restart_only(startup: ProxyConfig, candidate: ProxyConfig) -> ReloadOutcome:
    """Keep restart-only values at what the process started with.

    Returning the candidate untouched would make `current` report a proxy URL the process is not using, since those values are read once while wiring startup.
    """
    startup_values = startup.model_dump(mode="python")
    candidate_values = candidate.model_dump(mode="python")

    pinned: set[str] = set()
    counting_providers_explicit = (
        "providers" in candidate.inbound.anthropic_count_tokens.model_fields_set
    )
    graph_changed = _pin_provider_graph(startup_values, candidate_values, pinned)
    if graph_changed:
        _pin_provider_graph_selectors(startup_values, candidate_values, pinned)
        counting_providers_explicit = (
            "providers" in startup.inbound.anthropic_count_tokens.model_fields_set
        )
    _pin_type_scoped_provider_fields(startup_values, candidate_values, pinned)

    for pattern in sorted(NOT_HOT_RELOADABLE):
        seen: set[tuple[str, ...]] = set()
        for path in (*_expand(pattern, startup_values), *_expand(pattern, candidate_values)):
            if path in seen:
                continue
            seen.add(path)
            was = _read(startup_values, path)
            now = _read(candidate_values, path)
            if was != now:
                _write(candidate_values, path, was)
                pinned.add(".".join(path))

    # `model_dump` materialises defaults, but this validator intentionally distinguishes an inherited default from an operator-written provider list. Preserve that distinction across the round trip or a deployment whose only provider is not named `ghc` fails its first reload on a value nobody wrote.
    if not counting_providers_explicit:
        inbound = cast(dict[str, Any], candidate_values["inbound"])
        counting = cast(dict[str, Any], inbound["anthropic_count_tokens"])
        counting.pop("providers", None)

    effective = ProxyConfig.model_validate(candidate_values)
    return ReloadOutcome(
        config=effective,
        changed=effective != startup,
        restart_required=tuple(sorted(pinned)),
    )


class ConfigProvider:
    """Single reader of the effective configuration.

    Consumers take a snapshot when they start a unit of work and keep it for that work's lifetime.
    A request that began under one version therefore finishes under it.
    """

    def __init__(self, initial: ProxyConfig, *, source: Callable[[], ProxyConfig]) -> None:
        self._startup = initial
        self._current = initial
        self._source = source

    @property
    def current(self) -> ProxyConfig:
        return self._current

    @property
    def startup(self) -> ProxyConfig:
        return self._startup

    def reload(self) -> ReloadOutcome:
        """Rebuild from the source and swap in the result.

        A failure to build propagates and leaves the current snapshot untouched.
        A bad edit therefore cannot take the process down to an unconfigured state.
        """
        outcome = pin_restart_only(self._startup, self._source())
        self._current = outcome.config
        return outcome
