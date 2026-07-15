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
    monkeypatch.setenv("GHC_PORT", "4300")
    monkeypatch.setenv("GHC_OBSERVABILITY__LOG_LEVEL", "ERROR")

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
    monkeypatch.setenv("GHC_MODEL_MAPPINGS", '{"env-model":"env-target"}')

    settings = load_settings(
        config_path=config_path,
        cli_overrides={
            "model_mappings": {"cli-model": "cli-target"},
            "timeouts": {"stream_idle_overrides": {"cli-model": 700}},
        },
    )

    assert settings.model_mappings == {
        "yaml-model": "yaml-target",
        "env-model": "env-target",
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