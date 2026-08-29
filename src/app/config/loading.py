"""Five-level configuration loading for `ProxyConfig`, per `config.example.yaml`.

Priority, highest first: CLI options, environment variables, the user config file.
Then the bundled config shipped with the distribution, then the schema defaults.

This is the loader **every** entry point uses, `--fd` included: `cli.py` reaches the socket-activated path through `_load_spec_config` and `serve_inherited`, the same as the direct run. `app.config.loader`, one letter away, loads the old `AppSettings` — which as of 2026-08-22 configures only the legacy chain and has no caller in `src/` beyond a re-export. The two are not interchangeable, and this docstring used to hand `--fd` to the other one.
"""

import os
from collections.abc import Mapping
from importlib import resources
from pathlib import Path
from typing import Any, cast

import yaml

from app.config.paths import expand_user_path, spec_config_file_path
from app.config.schema import ProxyConfig

# The distribution is `ghc-api-proxy`, and the prefix says so in full. `GHC_` alone named GitHub Copilot rather than this proxy, which put every setting of ours in the same namespace as anything else that talks to the same upstream. Ruled 2026-08-22.
ENV_PREFIX = "GHC_API_PROXY_"
ENV_NESTED_DELIMITER = "__"
BUNDLED_CONFIG_RESOURCE = "bundled-config.yaml"
# Names the file to read, so it is not one of the settings inside it. Left in, it would be read as a top-level `config` key and `ProxyConfig` forbids unknown ones — the variable would break start-up rather than select a file.
CONFIG_PATH_VARIABLE = f"{ENV_PREFIX}CONFIG"
# The GitHub token `app.model_provider.ghc_client.auth.providers.EnvTokenProvider` reads. Excluded for the same reason as the one above and not a variation on it: it shares the prefix, so left in it arrives as a top-level `github_token` key and refuses to start. Named here rather than in the auth module because this is where the prefix that creates the collision is defined.
GITHUB_TOKEN_VARIABLE = f"{ENV_PREFIX}GITHUB_TOKEN"
NON_SETTING_VARIABLES = frozenset({CONFIG_PATH_VARIABLE, GITHUB_TOKEN_VARIABLE})

# Flat spellings the prefix makes natural, pointed at where the schema actually keeps them. Nesting is by `__`, so `GHC_API_PROXY_PORT` would otherwise arrive as a top-level `port` key and hit the same collision the two variables above are excluded for, with the same result: the service refuses to start, naming a field nobody set. It is the obvious way to say it, and `config.example.yaml` uses that spelling when it names the pidfile — so it is going to be typed. `host` is aliased alongside it rather than on its own merit: the two are set together, and aliasing one would leave the other as exactly the trap this removes.
ENV_ALIASES: Mapping[str, tuple[str, ...]] = {
    "host": ("server", "host"),
    "port": ("server", "port"),
}


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


# Every field in `ProxyConfig` that holds a filesystem path, as a dotted route into the merged mapping. `*` matches one level of keys, which is how `model_providers` is reached without naming the providers an operator invented. Kept as data rather than as a validator per field so that adding a path field is one line here and not a rule rewritten in three places — and so that the list of what counts as a path is readable in one place, which is what `_rebase_configured_paths` needs to be auditable at all.
_PATH_FIELDS: tuple[tuple[str, ...], ...] = (
    ("server", "tls", "cert"),
    ("server", "tls", "key"),
    ("model_providers", "*", "github_token_file"),
    ("pidfile_dir",),
)


def _rebase_configured_paths(values: Mapping[str, Any], base_dir: Path) -> dict[str, Any]:
    """Make every relative path the config file declares absolute against the file's own directory.

    Ruled by the user 2026-08-28: a relative path in `config.yaml` is read relative to `config.yaml`, never to the working directory the command happened to start in. The directory a service was launched from should not decide where its token is written — the same reasoning `resolve_config_path` already applies to which file gets read at all.

    **Only the file layer is rebased.** A relative path arriving from the environment or a CLI option keeps shell semantics, because someone typing `--pidfile-dir ./run` means the directory they are standing in, and silently resolving that against a config file elsewhere would be its own ambush. When no config file was found there is nothing to rebase against and nothing is rewritten.

    Expansion runs first: `~`, `$VAR` and the spec's `$XDG_DATA_HOME/ghc-api-proxy` spelling all produce absolute paths on their own, and only what is still relative afterwards is joined to `base_dir`. Downstream consumers keep calling `expand_user_path` or `Path(...)` unchanged, because expanding an already-absolute path is a no-op.
    """
    result = dict(values)
    for field in _PATH_FIELDS:
        _rebase_at(result, field, base_dir)
    return result


def _rebase_at(node: dict[str, Any], field: tuple[str, ...], base_dir: Path) -> None:
    head, rest = field[0], field[1:]
    if head == "*":
        for key in list(node):
            child = node.get(key)
            if isinstance(child, dict):
                _rebase_at(cast(dict[str, Any], child), rest, base_dir)
        return
    if not rest:
        value = node.get(head)
        # Only a non-empty string is a path anyone wrote. An absent key, an empty one (the schema default, meaning "use the built-in location"), and anything that is not a string all belong to layers this function does not decide — the schema reports a wrong type with the field name attached, which is a better message than one from here.
        if isinstance(value, str) and value.strip():
            expanded = expand_user_path(value)
            node[head] = str(expanded if expanded.is_absolute() else base_dir / expanded)
        return
    child = node.get(head)
    if isinstance(child, dict):
        _rebase_at(cast(dict[str, Any], child), rest, base_dir)


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


def bundled_config_text() -> str:
    """The shipped config as written, comments and all.

    Separate from `bundled_config_values`: that one is for layering, this one is for handing the operator a file to edit, and the comments are most of what makes it worth handing over.
    """
    resource = resources.files("app.config").joinpath(BUNDLED_CONFIG_RESOURCE)
    return resource.read_text(encoding="utf-8") if resource.is_file() else ""


def resolve_config_path(explicit_path: Path | None) -> Path | None:
    """Locate the user config file: `--config`, then the environment, then the spec's location.

    An explicitly named file that does not exist is an error.
    The default location simply being absent is not.

    **A `config.yaml` in the working directory is not consulted.** It was, because the path this replaced honoured it, and dropping it then would have changed how operators start the service as a side effect of swapping the schema rather than as a decision. Ruled 2026-08-22, and the decision is now made: which directory a service was launched from should not decide what it runs. It reads as a convenience and behaves as an ambush — starting the proxy from a checkout of some other project silently adopted that project's config, and the failure it produced named a key rather than a file.
    """
    if explicit_path is not None:
        if not explicit_path.is_file():
            raise FileNotFoundError(f"configuration file not found: {explicit_path}")
        return explicit_path

    env_path = os.environ.get(CONFIG_PATH_VARIABLE)
    if env_path:
        resolved = Path(env_path)
        if not resolved.is_file():
            raise FileNotFoundError(f"configuration file not found: {resolved}")
        return resolved

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
    """Read `GHC_API_PROXY_`-prefixed variables, nesting on `__`.

    Values stay strings; pydantic coerces them. YAML-ish parsing here would make `off` and `both` behave differently between the file and the environment.

    A name with no `__` in it is looked up in `ENV_ALIASES` first, so the flat spellings an operator reaches for land where the schema keeps them instead of on a top-level key it forbids.

    Aliased names are collected separately and merged under the explicit ones, so setting both spellings of the same setting resolves the same way every time. Merging them in one pass would let the answer depend on which name the environment happened to yield first.
    """
    source = environ if environ is not None else os.environ
    aliased: dict[str, Any] = {}
    explicit: dict[str, Any] = {}
    for name, raw in source.items():
        if not name.startswith(ENV_PREFIX) or name in NON_SETTING_VARIABLES:
            continue
        remainder = name[len(ENV_PREFIX) :].lower()
        if not remainder:
            continue
        path = tuple(remainder.split(ENV_NESTED_DELIMITER))
        if len(path) == 1 and path[0] in ENV_ALIASES:
            _assign(aliased, ENV_ALIASES[path[0]], raw)
        else:
            _assign(explicit, path, raw)
    return _deep_merge(aliased, explicit)


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
        # Rebased before merging, so only the paths this file declares are affected — an environment or CLI value keeps shell semantics. Ruled 2026-08-28; see `_rebase_configured_paths`.
        layers.append(
            _rebase_configured_paths(_read_yaml(resolved_path), resolved_path.parent.absolute())
        )
    layers.append(environment_values(environ))
    layers.append({key: value for key, value in (cli_overrides or {}).items() if value is not None})

    merged: dict[str, Any] = {}
    for layer in layers:
        merged = _deep_merge(merged, layer)
    return ProxyConfig.model_validate(merged)
