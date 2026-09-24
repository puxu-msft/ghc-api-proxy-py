import os
import re
from importlib import resources
from pathlib import Path

from platformdirs import user_config_path as platform_user_config_path
from platformdirs import user_data_path as platform_user_data_path

APP_NAME = "ghc-api-proxy"

# The name a configured path may use for the installed package itself. A uvx run
# has no checkout, so `contrib/` does not exist for it — while a file inside the
# package ships in the wheel and resolves through `importlib.resources` however the
# distribution was installed. It is substituted before anything else reads the text,
# so it composes with the `${VAR:-fallback}` pass and with `~` below.
PACKAGE_DIR_VARIABLE = "GHC_PACKAGE_DIR"
_PACKAGE_DIR_SPELLINGS = (
    f"${PACKAGE_DIR_VARIABLE}",
    "${" + PACKAGE_DIR_VARIABLE + "}",
)


def package_dir() -> Path:
    """Where the installed `app` package lives.

    One fact with one source: `importlib.resources` answers it for an editable
    install and for an isolated uvx cache alike, so there is deliberately no
    environment-variable override for this name.
    """
    return Path(str(resources.files("app")))

# A shell's `${VAR:-fallback}`, which `os.path.expandvars` does not know: it treats
# `VAR:-fallback` as a variable name that is never set and leaves the whole token in
# the path. Writing a fallback is the entire point of the form — the file it names
# lives at a location the variable may not carry yet on the machine reading it.
_DEFAULTED_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*):-([^}]*)\}")


def _apply_shell_defaults(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name, fallback = match.group(1), match.group(2)
        value = os.environ.get(name)
        if value:
            return value
        # The fallback is expanded here rather than left to `expanduser` below, which
        # only ever sees the first character of the result.
        return str(Path(fallback).expanduser()) if fallback.startswith("~") else fallback

    return _DEFAULTED_VARIABLE.sub(replace, text)


def user_config_path() -> Path:
    return platform_user_config_path(APP_NAME, ensure_exists=False)


def user_data_path() -> Path:
    return platform_user_data_path(APP_NAME, ensure_exists=False)


def config_file_path() -> Path:
    return user_config_path() / "config.yaml"


def spec_config_file_path() -> Path:
    """The config file location the human-controlled spec names.

    Deliberately under XDG_DATA rather than XDG_CONFIG; the spec places the pidfile there too.
    """
    return user_data_path() / "config.yaml"


def standalone_pidfile_path(port: int, directory: Path | None = None) -> Path:
    """Where the stand-alone pidfile lives, inside `directory` or the default data directory.

    Named after the port because the file identifies one listening endpoint, not one installation.
    A single shared name made every `start` a claimant to the same record regardless of what it was listening on: a throwaway run on another port overwrote the incumbent's entry on its way up and deleted it on its way down, after which the incumbent existed but could no longer be found.
    The next `--restart` then had no predecessor to signal and quietly became a second listener on the same port instead of a replacement, which is the one failure that looks exactly like success.

    The operator configures the directory rather than the file, so that one setting covers however many ports they run; the name inside it is not theirs to choose, because a successor has to be able to derive it from nothing but the port it is taking over.
    """
    return (directory if directory is not None else user_data_path()) / f"standalone-{port}.pid"


def tokenization_state_path() -> Path:
    """Where the calibration and prompt-limit state lives.

    Derived rather than configured: `config.example.yaml` has no `tokenization` section, and the `local` token counter is useless without somewhere to keep what it has learnt. Naming the location here keeps that working without inventing a config key the spec does not have.
    """
    return user_data_path() / "tokenization.json"


def tokenization_learning_path() -> Path:
    """Where versioned token-prediction history lives."""
    return user_data_path() / "tokenization-learning.sqlite3"


def debug_capture_rules_path() -> Path:
    """Where HTTP-managed raw-capture selection rules live."""
    return user_data_path() / "debug-capture-rules.sqlite3"


def tls_material_dir() -> Path:
    """Where a generated self-signed pair is kept.

    `config.example.yaml` says `<config-dir>/tls/`, and the config directory is the one holding the config file — which the user placed under `$XDG_DATA_HOME`. A fixed location rather than the directory the config happened to be read from: a `config.yaml` picked up from the working directory would otherwise scatter key material into whatever tree the service was started in.
    """
    return user_data_path() / "tls"


def expand_user_path(value: str) -> Path:
    """Expand a configured path the way the spec writes them.

    The spec spells locations as `$XDG_DATA_HOME/...`, and that variable is usually unset.
    `os.path.expandvars` would leave it as a literal directory name, so platformdirs resolves it.
    `~` and other variables expand normally, and a `${VAR:-fallback}` picks the fallback when the
    variable is unset or empty. `${GHC_PACKAGE_DIR}` names the installed package itself and is
    substituted first, from `importlib.resources` rather than the environment.
    """
    text = value.strip()
    for spelling in _PACKAGE_DIR_SPELLINGS:
        text = text.replace(spelling, str(package_dir()))
    for spelling in ("$XDG_DATA_HOME/ghc-api-proxy", "${XDG_DATA_HOME}/ghc-api-proxy"):
        if text.startswith(spelling) and "XDG_DATA_HOME" not in os.environ:
            return user_data_path() / text[len(spelling) :].lstrip("/")
    return Path(os.path.expandvars(_apply_shell_defaults(text))).expanduser()
