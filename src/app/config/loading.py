"""Five-level configuration loading, per `config.example.yaml`.

Priority, highest first: CLI options, environment variables, the user config file.
Then the bundled config shipped with the distribution, then the schema defaults.
"""

import os
from collections.abc import Mapping
from importlib import resources
from pathlib import Path
from typing import Any, cast

import yaml

from app.config.paths import spec_config_file_path
from app.config.schema import ProxyConfig

ENV_PREFIX = "GHC_"
ENV_NESTED_DELIMITER = "__"
BUNDLED_CONFIG_RESOURCE = "bundled-config.yaml"


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Merge mappings key by key; anything else replaces wholesale.

    Per-key merging lets a user config override only the keys it names.
    That is how the spec tells operators to write one. Lists replace, so removal stays possible.
    """
    result = dict(base)
    for key, value in override.items():
        current = result.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            result[key] = _deep_merge(
                cast(Mapping[str, Any], current),
                cast(Mapping[str, Any], value),
            )
        else:
            result[key] = value
    return result


def _read_yaml(path: Path) -> dict[str, Any]:
    loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"configuration file must contain a mapping: {path}")
    return cast(dict[str, Any], loaded)


def bundled_config_values() -> dict[str, Any]:
    resource = resources.files("app.config").joinpath(BUNDLED_CONFIG_RESOURCE)
    if not resource.is_file():
        return {}
    loaded: object = yaml.safe_load(resource.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError("bundled configuration must contain a mapping")
    return cast(dict[str, Any], loaded)


def resolve_config_path(explicit_path: Path | None) -> Path | None:
    """Locate the user config file.

    An explicitly named file that does not exist is an error.
    The default location simply being absent is not.
    """
    if explicit_path is not None:
        if not explicit_path.is_file():
            raise FileNotFoundError(f"configuration file not found: {explicit_path}")
        return explicit_path
    default_path = spec_config_file_path()
    return default_path if default_path.is_file() else None


def _assign(target: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cursor = target
    for key in path[:-1]:
        existing = cursor.get(key)
        if not isinstance(existing, dict):
            existing = {}
            cursor[key] = existing
        cursor = cast(dict[str, Any], existing)
    cursor[path[-1]] = value


def environment_values(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Read `GHC_`-prefixed variables, nesting on `__`.

    Values stay strings; pydantic coerces them. YAML-ish parsing here would make `off` and `both`
    behave differently between the file and the environment.
    """
    source = environ if environ is not None else os.environ
    values: dict[str, Any] = {}
    for name, raw in source.items():
        if not name.startswith(ENV_PREFIX):
            continue
        remainder = name[len(ENV_PREFIX) :].lower()
        if not remainder:
            continue
        _assign(values, tuple(remainder.split(ENV_NESTED_DELIMITER)), raw)
    return values


def load_proxy_config(
    *,
    config_path: Path | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
    bundled: Mapping[str, Any] | None = None,
) -> ProxyConfig:
    layers: list[Mapping[str, Any]] = [
        bundled if bundled is not None else bundled_config_values(),
    ]
    resolved_path = resolve_config_path(config_path)
    if resolved_path is not None:
        layers.append(_read_yaml(resolved_path))
    layers.append(environment_values(environ))
    layers.append({key: value for key, value in (cli_overrides or {}).items() if value is not None})

    merged: dict[str, Any] = {}
    for layer in layers:
        merged = _deep_merge(merged, layer)
    return ProxyConfig.model_validate(merged)
