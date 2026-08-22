"""Loading for the *old* `AppSettings`, which no longer serves any production path.

This docstring used to say it served the `--fd` (systemd) path, and that stopped being true without anything noticing. `cli.py` reaches `--fd` through `_load_spec_config` -> `ProxyConfig` -> `serve_inherited`, the same as the direct-run path; `tests/systemd/test_systemd_units.py` already says as much in passing. As of 2026-08-22 `load_settings` has no caller in `src/` beyond `app.config.__init__` re-exporting it, and its only exercise is `tests/unit/config/test_config_loader.py`. It is kept because `AppSettings` still configures the legacy chain (`app.routes` / `AnthropicClient` / `app.deps`), which is present and not deleted; nothing on the new chain reads it.

Not to be confused with `app.config.loading`, one letter away, which loads the spec's `ProxyConfig` and is what every entry point now uses. The names are close enough that this one was found first and its neighbour rewritten from scratch once; the two are not interchangeable.
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from pydantic_settings import YamlConfigSettingsSource

from app.config.compat import migrate_compat
from app.config.loading import CONFIG_PATH_VARIABLE
from app.config.paths import config_file_path
from app.config.settings import AppSettings, EnvSourceWithoutWholeValues

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

    env_path = os.environ.get(CONFIG_PATH_VARIABLE)
    if env_path:
        resolved_env_path = Path(env_path)
        if not resolved_env_path.is_file():
            raise FileNotFoundError(f"configuration file not found: {resolved_env_path}")
        return resolved_env_path

    # No `config.yaml` from the working directory; see `app.config.loading.resolve_config_path`, which is where that ruling is written down and which this path has to agree with.
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

    # The source `AppSettings` itself validates through, so this layer and the validation below cannot disagree about which spellings the environment may carry.
    env_values = EnvSourceWithoutWholeValues(AppSettings)()
    cli_values = {key: value for key, value in (cli_overrides or {}).items() if value is not None}

    merged = _merge_layers(defaults, yaml_values)
    merged = _merge_layers(merged, env_values)
    merged = _merge_layers(merged, cli_values)
    return AppSettings.model_validate(merged)
