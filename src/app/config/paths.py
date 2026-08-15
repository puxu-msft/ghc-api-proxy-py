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