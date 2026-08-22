import os
from pathlib import Path

from platformdirs import user_config_path as platform_user_config_path
from platformdirs import user_data_path as platform_user_data_path

APP_NAME = "ghc-api-proxy"


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


def standalone_pidfile_path(port: int) -> Path:
    """Where the stand-alone pidfile lives when the operator names none.

    Named after the port because the file identifies one listening endpoint, not one installation.
    A single shared name made every `start` a claimant to the same record regardless of what it was listening on: a throwaway run on another port overwrote the incumbent's entry on its way up and deleted it on its way down, after which the incumbent existed but could no longer be found.
    The next `--restart` then had no predecessor to signal and quietly became a second listener on the same port instead of a replacement, which is the one failure that looks exactly like success.
    """
    return user_data_path() / f"standalone-{port}.pid"


def tokenization_state_path() -> Path:
    """Where the calibration and prompt-limit state lives.

    Derived rather than configured: `config.example.yaml` has no `tokenization` section, and the
    `local` token counter is useless without somewhere to keep what it has learnt. Naming the
    location here keeps that working without inventing a config key the spec does not have.
    """
    return user_data_path() / "tokenization.json"



def tls_material_dir() -> Path:
    """Where a generated self-signed pair is kept.

    `config.example.yaml` says `<config-dir>/tls/`, and the config directory is the one holding
    the config file — which the user placed under `$XDG_DATA_HOME`. A fixed location rather than
    the directory the config happened to be read from: a `config.yaml` picked up from the working
    directory would otherwise scatter key material into whatever tree the service was started in.
    """
    return user_data_path() / "tls"


def expand_user_path(value: str) -> Path:
    """Expand a configured path the way the spec writes them.

    The spec spells locations as `$XDG_DATA_HOME/...`, and that variable is usually unset.
    `os.path.expandvars` would leave it as a literal directory name, so platformdirs resolves it.
    `~` and other variables expand normally.
    """
    text = value.strip()
    for spelling in ("$XDG_DATA_HOME/ghc-api-proxy", "${XDG_DATA_HOME}/ghc-api-proxy"):
        if text.startswith(spelling) and "XDG_DATA_HOME" not in os.environ:
            return user_data_path() / text[len(spelling) :].lstrip("/")
    return Path(os.path.expandvars(text)).expanduser()
