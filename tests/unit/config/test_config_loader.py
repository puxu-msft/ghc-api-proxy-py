from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config.compat import migrate_compat
from app.config.loader import load_settings
from app.config.paths import config_file_path, user_config_path, user_data_path
from app.config.settings import AppSettings


def test_four_layer_merge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "port: 4200\n"
        "upstream:\n"
        "  max_connections: 150\n"
        "observability:\n"
        "  log_level: WARNING\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GHC_API_PROXY_PORT", "4300")
    monkeypatch.setenv("GHC_API_PROXY_OBSERVABILITY__LOG_LEVEL", "ERROR")

    settings = load_settings(
        config_path=config_path,
        cli_overrides={"port": 4400, "debug": True},
    )

    assert settings.host == "127.0.0.1"
    assert settings.upstream.max_connections == 150
    assert settings.observability.log_level == "ERROR"
    assert settings.port == 4400
    assert settings.debug is True


def test_per_key_merge_model_mappings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "model_mappings:\n"
        "  yaml-model: yaml-target\n"
        "timeouts:\n"
        "  stream_idle_overrides:\n"
        "    yaml-model: 500\n",
        encoding="utf-8",
    )
    # No environment layer here: `model_mappings` is one of `NON_ENVIRONMENT_SETTINGS`, so the merge this asserts is between the file and the CLI.
    settings = load_settings(
        config_path=config_path,
        cli_overrides={
            "model_mappings": {"cli-model": "cli-target"},
            "timeouts": {"stream_idle_overrides": {"cli-model": 700}},
        },
    )

    assert settings.model_mappings == {
        "yaml-model": "yaml-target",
        "cli-model": "cli-target",
    }
    assert settings.timeouts.stream_idle_overrides == {
        "gpt-5.5": 600,
        "yaml-model": 500,
        "cli-model": 700,
    }


def test_non_per_key_mapping_is_replaced(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "anthropic:\n"
        "  effort_overrides:\n"
        "    yaml-model:\n"
        "      - high\n",
        encoding="utf-8",
    )

    settings = load_settings(
        config_path=config_path,
        cli_overrides={
            "anthropic": {"effort_overrides": {"cli-model": ["low"]}},
        },
    )

    assert settings.anthropic.effort_overrides == {"cli-model": ["low"]}


def test_shutdown_graceful_timeout_uses_normal_config_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "shutdown:\n"
        "  graceful_timeout: 11\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GHC_API_PROXY_SHUTDOWN__GRACEFUL_TIMEOUT", "12")

    settings = load_settings(
        config_path=config_path,
        cli_overrides={"shutdown": {"graceful_timeout": 13}},
    )

    assert settings.shutdown.graceful_timeout == 13


def test_shutdown_drain_timeout_defaults_to_infinite_and_accepts_positive_value() -> None:
    assert AppSettings().shutdown.drain_timeout == 0
    settings = AppSettings.model_validate({"shutdown": {"drain_timeout": 17}})
    assert settings.shutdown.drain_timeout == 17


def test_model_overrides_mapping_is_replaced(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "model_overrides:\n"
        "  custom: yaml-target\n",
        encoding="utf-8",
    )

    settings = load_settings(config_path=config_path)

    assert settings.model_overrides == {"custom": "yaml-target"}


def test_ghc_config_environment_selects_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "from-env.yaml"
    config_path.write_text("port: 4567\n", encoding="utf-8")
    monkeypatch.setenv("GHC_API_PROXY_CONFIG", str(config_path))

    assert load_settings().port == 4567


def test_explicit_missing_config_is_an_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError, match=str(missing_path)):
        load_settings(config_path=missing_path)


def test_missing_ghc_config_environment_is_an_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_path = tmp_path / "missing-from-env.yaml"
    monkeypatch.setenv("GHC_API_PROXY_CONFIG", str(missing_path))

    with pytest.raises(FileNotFoundError, match=str(missing_path)):
        load_settings()


def test_compat_migration_warns_and_preserves_explicit_new_keys() -> None:
    with pytest.warns(DeprecationWarning) as warnings:
        migrated = migrate_compat(
            {
                "history": {"limit": 75, "success_limit": 50},
                "timeouts": {"stream_idle_timeout": 90, "fetch_timeout": 120},
            }
        )

    messages = {str(warning.message) for warning in warnings}
    assert any("history.limit" in message for message in messages)
    assert any("timeouts.stream_idle_timeout" in message for message in messages)
    assert any("timeouts.fetch_timeout" in message for message in messages)
    assert migrated["history"] == {"success_limit": 50, "failure_limit": 75}
    assert migrated["timeouts"] == {"stream_idle": 90, "response_header": 120}


def test_settings_are_frozen() -> None:
    settings = AppSettings()

    with pytest.raises(ValidationError):
        settings.port = 9000


def test_platform_paths_honor_xdg_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_home = tmp_path / "config-home"
    data_home = tmp_path / "data-home"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))

    assert user_config_path() == config_home / "ghc-api-proxy"
    assert user_data_path() == data_home / "ghc-api-proxy"
    assert config_file_path() == config_home / "ghc-api-proxy" / "config.yaml"
