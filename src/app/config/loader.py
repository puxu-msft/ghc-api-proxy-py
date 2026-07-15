import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from pydantic_settings import EnvSettingsSource, YamlConfigSettingsSource

from app.config.compat import migrate_compat
from app.config.paths import config_file_path
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
        ("rate_limiter",),
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