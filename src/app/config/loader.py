import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic_settings import EnvSettingsSource, YamlConfigSettingsSource

from app.config.compat import migrate_compat
from app.config.paths import bundled_config_path, config_file_path, spec_config_file_path
from app.config.schema import ProxyConfig
from app.config.settings import AppSettings

PER_KEY_PATHS = frozenset(
    {
        ("model_mappings",),
        ("timeouts", "stream_idle_overrides"),
        ("timeouts", "response_header_overrides"),
    }
)
SECTION_PATHS = frozenset(
    {
        ("anthropic",),
        ("approval",),
        ("auth",),
        ("history",),
        ("headers",),
        ("observability",),
        ("openai_responses",),
        ("rate_limiter",),
        ("shutdown",),
        ("timeouts",),
        ("upstream",),
    }
)


def _merge_layers(
    base: Mapping[str, Any],
    override: Mapping[str, Any],
    path: tuple[str, ...] = (),
) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        current_path = (*path, key)
        current_value = result.get(key)
        if (
            isinstance(current_value, Mapping)
            and isinstance(value, Mapping)
            and (current_path in PER_KEY_PATHS or current_path in SECTION_PATHS)
        ):
            result[key] = _merge_layers(
                cast(Mapping[str, Any], current_value),
                cast(Mapping[str, Any], value),
                current_path,
            )
        else:
            result[key] = value
    return result


def _resolve_config_path(explicit_path: Path | None) -> Path | None:
    if explicit_path is not None:
        if not explicit_path.is_file():
            raise FileNotFoundError(f"configuration file not found: {explicit_path}")
        return explicit_path

    env_path = os.environ.get("GHC_CONFIG")
    if env_path:
        resolved_env_path = Path(env_path)
        if not resolved_env_path.is_file():
            raise FileNotFoundError(f"configuration file not found: {resolved_env_path}")
        return resolved_env_path

    local_path = Path.cwd() / "config.yaml"
    if local_path.is_file():
        return local_path

    default_path = config_file_path()
    return default_path if default_path.is_file() else None


def load_settings(
    *,
    config_path: Path | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
) -> AppSettings:
    defaults = AppSettings.model_validate({}).model_dump(mode="python")

    resolved_path = _resolve_config_path(config_path)
    yaml_values: dict[str, Any] = {}
    if resolved_path is not None:
        yaml_values = migrate_compat(
            YamlConfigSettingsSource(AppSettings, yaml_file=resolved_path)()
        )

    env_values = EnvSettingsSource(AppSettings)()
    cli_values = {key: value for key, value in (cli_overrides or {}).items() if value is not None}

    merged = _merge_layers(defaults, yaml_values)
    merged = _merge_layers(merged, env_values)
    merged = _merge_layers(merged, cli_values)
    return AppSettings.model_validate(merged)

def _resolve_proxy_config_path(explicit_path: Path | None) -> Path | None:
    """Where the spec's config file lives, or None when there is none to read.

    Same search order as `_resolve_config_path`, with one deliberate difference at the end: the
    default sits under `$XDG_DATA_HOME` rather than `$XDG_CONFIG_HOME`, because that is where the
    user's spec places it.
    """
    if explicit_path is not None:
        if not explicit_path.is_file():
            raise FileNotFoundError(f"configuration file not found: {explicit_path}")
        return explicit_path

    env_path = os.environ.get("GHC_CONFIG")
    if env_path:
        resolved_env_path = Path(env_path)
        if not resolved_env_path.is_file():
            raise FileNotFoundError(f"configuration file not found: {resolved_env_path}")
        return resolved_env_path

    local_path = Path.cwd() / "config.yaml"
    if local_path.is_file():
        return local_path

    default_path = spec_config_file_path()
    return default_path if default_path.is_file() else None


def load_proxy_config(
    *,
    config_path: Path | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
) -> ProxyConfig:
    """Read the spec's configuration.

    No environment layer, unlike `load_settings`. `ProxyConfig` forbids unknown keys, and the spec
    does not define an environment spelling for any of them; inventing one here would make the
    config contract something this file decided rather than something the spec states.
    """
    resolved_path = _resolve_proxy_config_path(config_path)
    yaml_values = _read_yaml_mapping(resolved_path) if resolved_path is not None else {}

    # The shipped file is the base layer, not a fallback for when the user has none. A user config
    # that sets only `server.port` still needs a provider, and `model_providers` has no schema
    # default that would supply one — routing fails closed, so an empty catalog refuses everything.
    merged = _merge_layers(_read_yaml_mapping(bundled_config_path()), yaml_values)
    merged = _merge_layers(merged, dict(cli_overrides or {}))
    return ProxyConfig.model_validate(merged)


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    """Parse a YAML file that must describe a mapping.

    Read directly rather than through pydantic-settings: `ProxyConfig` is a plain model, and those
    settings sources are built for `BaseSettings`.
    """
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    if parsed is not None and not isinstance(parsed, dict):
        raise ValueError(f"configuration file must contain a mapping: {path}")
    return cast(dict[str, Any], parsed or {})
