from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config.loading import environment_values, load_proxy_config, resolve_config_path
from app.config.paths import spec_config_file_path
from app.config.provider import ConfigProvider, pin_restart_only
from app.config.schema import ProxyConfig


def write_config(directory: Path, body: str) -> Path:
    path = directory / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_spec_config_path_is_under_xdg_data(monkeypatch: pytest.MonkeyPatch) -> None:
    # The spec puts the config file under XDG_DATA, not the XDG_CONFIG the old loader used.
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/probe-data")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/probe-config")
    resolved = str(spec_config_file_path())
    assert resolved.startswith("/tmp/probe-data")
    assert "probe-config" not in resolved


def test_each_layer_beats_the_one_below(tmp_path: Path) -> None:
    path = write_config(tmp_path, "graceful_cleanup_timeout: 30\n")
    config = load_proxy_config(
        config_path=path,
        bundled={"graceful_cleanup_timeout": 10},
    )
    assert config.graceful_cleanup_timeout == 30

    config = load_proxy_config(
        config_path=path,
        bundled={"graceful_cleanup_timeout": 10},
        environ={"GHC_GRACEFUL_CLEANUP_TIMEOUT": "40"},
    )
    assert config.graceful_cleanup_timeout == 40

    config = load_proxy_config(
        config_path=path,
        bundled={"graceful_cleanup_timeout": 10},
        environ={"GHC_GRACEFUL_CLEANUP_TIMEOUT": "40"},
        cli_overrides={"graceful_cleanup_timeout": 50},
    )
    assert config.graceful_cleanup_timeout == 50


def test_bundled_layer_applies_when_nothing_overrides_it() -> None:
    config = load_proxy_config(bundled={"graceful_cleanup_timeout": 10}, environ={})
    assert config.graceful_cleanup_timeout == 10


def test_user_file_overrides_only_the_keys_it_names(tmp_path: Path) -> None:
    # The spec tells operators to copy only what they need, so a named key must not wipe siblings.
    path = write_config(tmp_path, "client_delivery:\n  sse_ping_interval: 5\n")
    config = load_proxy_config(
        config_path=path,
        bundled={"client_delivery": {"buffering_policy": "full", "sse_ping_interval": 99}},
        environ={},
    )
    assert config.client_delivery.sse_ping_interval == 5
    assert config.client_delivery.buffering_policy == "full"


def test_lists_replace_rather_than_accumulate(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        "model_providers:\n  ghc:\n    type: github_copilot\n    disabled_models: [only-this]\n",
    )
    config = load_proxy_config(
        config_path=path,
        bundled={
            "model_providers": {
                "ghc": {"type": "github_copilot", "disabled_models": ["a", "b", "c"]}
            }
        },
        environ={},
    )
    assert config.model_providers["ghc"].disabled_models == ["only-this"]


def test_environment_nests_on_double_underscore() -> None:
    values = environment_values({"GHC_CLIENT_DELIVERY__SSE_PING_INTERVAL": "7", "OTHER": "x"})
    assert values == {"client_delivery": {"sse_ping_interval": "7"}}


def test_missing_explicit_config_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        resolve_config_path(tmp_path / "absent.yaml")


def test_absent_default_config_file_is_not_an_error(monkeypatch: pytest.MonkeyPatch,
                                                    tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert resolve_config_path(None) is None


def test_invalid_config_value_is_rejected(tmp_path: Path) -> None:
    path = write_config(tmp_path, "client_delivery:\n  buffering_policy: nonsense\n")
    with pytest.raises(ValidationError):
        load_proxy_config(config_path=path, bundled={}, environ={})


def test_restart_only_scalar_is_pinned_to_the_startup_value() -> None:
    startup = ProxyConfig.model_validate({"proxy": "http://old:1"})
    candidate = ProxyConfig.model_validate({"proxy": "http://new:2"})
    outcome = pin_restart_only(startup, candidate)
    # current must describe what the process is using; the http client was built with the old one.
    assert outcome.config.proxy == "http://old:1"
    assert outcome.restart_required == ("proxy",)


def test_restart_only_section_is_pinned_as_a_whole() -> None:
    startup = ProxyConfig()
    candidate = ProxyConfig.model_validate({"rate_limiter": {"retry_interval": 99}})
    outcome = pin_restart_only(startup, candidate)
    assert outcome.config.rate_limiter.retry_interval == 10
    assert outcome.restart_required == ("rate_limiter",)


def test_restart_only_wildcard_path_is_pinned_per_provider() -> None:
    startup = ProxyConfig.model_validate(
        {"model_providers": {"ghc": {"type": "github_copilot", "base_url": "https://old"}}}
    )
    candidate = ProxyConfig.model_validate(
        {
            "model_providers": {
                "ghc": {
                    "type": "github_copilot",
                    "base_url": "https://new",
                    "model_refresh_interval": 60,
                }
            }
        }
    )
    outcome = pin_restart_only(startup, candidate)
    assert outcome.config.model_providers["ghc"].base_url == "https://old"
    # A hot-reloadable sibling in the same section still takes effect.
    assert outcome.config.model_providers["ghc"].model_refresh_interval == 60
    assert outcome.restart_required == ("model_providers.ghc.base_url",)


def test_hot_reloadable_change_applies_without_being_reported() -> None:
    startup = ProxyConfig()
    candidate = ProxyConfig.model_validate({"client_delivery": {"sse_ping_interval": 3}})
    outcome = pin_restart_only(startup, candidate)
    assert outcome.config.client_delivery.sse_ping_interval == 3
    assert outcome.restart_required == ()
    assert outcome.changed is True


def test_provider_swaps_the_snapshot_on_reload() -> None:
    versions = [ProxyConfig(), ProxyConfig.model_validate({"graceful_cleanup_timeout": 5})]
    provider = ConfigProvider(versions[0], source=lambda: versions[1])
    held = provider.current

    outcome = provider.reload()

    assert outcome.changed is True
    assert provider.current.graceful_cleanup_timeout == 5
    # The snapshot a caller already took keeps its own values.
    assert held.graceful_cleanup_timeout == 60


def test_failed_reload_leaves_the_current_snapshot_in_place() -> None:
    def broken() -> ProxyConfig:
        raise ValueError("bad edit")

    provider = ConfigProvider(ProxyConfig(), source=broken)
    with pytest.raises(ValueError, match="bad edit"):
        provider.reload()
    assert provider.current.graceful_cleanup_timeout == 60
