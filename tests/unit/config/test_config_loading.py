from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config.loading import (
    CONFIG_PATH_VARIABLE,
    GITHUB_TOKEN_VARIABLE,
    environment_values,
    load_proxy_config,
    resolve_config_path,
)
from app.config.paths import spec_config_file_path
from app.config.provider import ConfigProvider, pin_restart_only
from app.config.schema import CodebuddyProviderConfig, GithubCopilotProviderConfig, ProxyConfig


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
        environ={"GHC_API_PROXY_GRACEFUL_CLEANUP_TIMEOUT": "40"},
    )
    assert config.graceful_cleanup_timeout == 40

    config = load_proxy_config(
        config_path=path,
        bundled={"graceful_cleanup_timeout": 10},
        environ={"GHC_API_PROXY_GRACEFUL_CLEANUP_TIMEOUT": "40"},
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
    values = environment_values({"GHC_API_PROXY_CLIENT_DELIVERY__SSE_PING_INTERVAL": "7", "OTHER": "x"})
    assert values == {"client_delivery": {"sse_ping_interval": "7"}}


def xingchen_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "type": "xingchen",
        "models": ["chat-pro"],
        "gateway_api_key": "gateway-key",
        "x_token": "complete.x.token",
        "device_id": "device-id",
        "install_id": "install-id",
    }
    values.update(overrides)
    return values


def test_nested_environment_overrides_xingchen_credentials() -> None:
    config = load_proxy_config(
        bundled={"model_providers": {"xingchen": xingchen_values()}},
        environ={
            "GHC_API_PROXY_MODEL_PROVIDERS__XINGCHEN__GATEWAY_API_KEY": "environment-key",
            "GHC_API_PROXY_MODEL_PROVIDERS__XINGCHEN__X_TOKEN": "environment.x.token",
        },
    )
    xingchen = config.model_providers["xingchen"]
    assert xingchen.type == "xingchen"
    assert xingchen.gateway_api_key == "environment-key"
    assert xingchen.x_token == "environment.x.token"


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
    candidate = ProxyConfig.model_validate({"reactive_rate_limiter": {"retry_interval": 99}})
    outcome = pin_restart_only(startup, candidate)
    assert outcome.config.reactive_rate_limiter.retry_interval == 10
    assert outcome.restart_required == ("reactive_rate_limiter",)


def test_restart_only_wildcard_path_is_pinned_per_provider() -> None:
    startup = ProxyConfig.model_validate(
        {"model_providers": {"ghc": {"type": "github_copilot", "api_base_url": "https://old"}}}
    )
    candidate = ProxyConfig.model_validate(
        {
            "model_providers": {
                "ghc": {
                    "type": "github_copilot",
                    "api_base_url": "https://new",
                    "model_refresh_interval": 60,
                }
            }
        }
    )
    outcome = pin_restart_only(startup, candidate)
    ghc = outcome.config.model_providers["ghc"]
    assert isinstance(ghc, GithubCopilotProviderConfig)
    assert ghc.api_base_url == "https://old"
    # A hot-reloadable sibling in the same section still takes effect.
    assert ghc.model_refresh_interval == 60
    assert outcome.restart_required == ("model_providers.ghc.api_base_url",)


def test_added_provider_is_pinned_out_as_one_graph_change() -> None:
    startup = ProxyConfig.model_validate(
        {"model_providers": {"ghc": {"type": "github_copilot"}}}
    )
    candidate = ProxyConfig.model_validate(
        {
            "model_providers": {
                "ghc": {"type": "github_copilot"},
                "xingchen": xingchen_values(),
            },
            "default_model_provider": "ghc",
        }
    )

    outcome = pin_restart_only(startup, candidate)

    assert set(outcome.config.model_providers) == {"ghc"}
    assert outcome.config.default_model_provider == ""
    assert outcome.restart_required == (
        "default_model_provider",
        "model_providers.xingchen",
    )


def test_provider_graph_change_restores_default_fallback_and_count_selectors() -> None:
    startup = ProxyConfig.model_validate(
        {
            "model_providers": {"ghc": {"type": "github_copilot"}},
            "default_model_provider": "ghc",
            "inbound": {
                "anthropic_count_tokens": {"providers": ["ghc", "local"]}
            },
        }
    )
    candidate = ProxyConfig.model_validate(
        {
            "model_providers": {
                "ghc": {"type": "github_copilot"},
                "xingchen": xingchen_values(),
            },
            "default_model_provider": "xingchen",
            "fallback_model_provider": "xingchen",
            "inbound": {
                "anthropic_count_tokens": {"providers": ["xingchen", "local"]}
            },
        }
    )

    outcome = pin_restart_only(startup, candidate)

    assert set(outcome.config.model_providers) == {"ghc"}
    assert outcome.config.default_model_provider == "ghc"
    assert outcome.config.fallback_model_provider == ""
    assert outcome.config.inbound.anthropic_count_tokens.providers == ["ghc", "local"]
    assert outcome.restart_required == (
        "default_model_provider",
        "fallback_model_provider",
        "inbound.anthropic_count_tokens.providers",
        "model_providers.xingchen",
    )


def test_graph_change_restores_an_implicit_count_selector_as_implicit() -> None:
    startup = ProxyConfig.model_validate(
        {
            "model_providers": {"only": {"type": "github_copilot"}},
            "default_model_provider": "only",
        }
    )
    candidate = ProxyConfig.model_validate(
        {
            "model_providers": {
                "only": {"type": "github_copilot"},
                "xingchen": xingchen_values(),
            },
            "default_model_provider": "only",
            "inbound": {
                "anthropic_count_tokens": {"providers": ["xingchen", "local"]}
            },
        }
    )

    outcome = pin_restart_only(startup, candidate)

    assert set(outcome.config.model_providers) == {"only"}
    assert outcome.config.inbound.anthropic_count_tokens.providers == ["ghc", "local"]
    assert "providers" not in outcome.config.inbound.anthropic_count_tokens.model_fields_set
    assert "inbound.anthropic_count_tokens.providers" in outcome.restart_required


def test_removed_provider_is_restored_as_one_graph_change() -> None:
    startup = ProxyConfig.model_validate(
        {
            "model_providers": {
                "ghc": {"type": "github_copilot"},
                "xingchen": xingchen_values(),
            },
            "default_model_provider": "ghc",
        }
    )
    candidate = ProxyConfig.model_validate(
        {
            "model_providers": {"ghc": {"type": "github_copilot"}},
            "default_model_provider": "ghc",
        }
    )

    outcome = pin_restart_only(startup, candidate)

    assert set(outcome.config.model_providers) == {"ghc", "xingchen"}
    assert outcome.restart_required == ("model_providers.xingchen",)


def test_provider_type_change_restores_the_whole_startup_variant() -> None:
    startup = ProxyConfig.model_validate(
        {"model_providers": {"same": {"type": "github_copilot", "auth_base_url": "https://api.github.com"}}}
    )
    candidate = ProxyConfig.model_validate(
        {"model_providers": {"same": xingchen_values()}}
    )

    outcome = pin_restart_only(startup, candidate)
    provider = outcome.config.model_providers["same"]

    assert provider.type == "github_copilot"
    assert provider.auth_base_url == "https://api.github.com"
    assert outcome.restart_required == ("model_providers.same",)


def test_xingchen_instance_fields_are_pinned_without_exposing_values() -> None:
    startup = ProxyConfig.model_validate(
        {"model_providers": {"xingchen": xingchen_values(disabled_models=["chat-lite"])}}
    )
    candidate = ProxyConfig.model_validate(
        {
            "model_providers": {
                "xingchen": xingchen_values(
                    models=["chat-next"],
                    gateway_api_key="new-key",
                    x_token="new.x.token",
                    device_id="new-device",
                    install_id="new-install",
                    app_version="3.0.0",
                    route_target="new-route",
                    client_type="new-client",
                    user_agent="new-agent",
                    disabled_models=["chat-pro"],
                )
            }
        }
    )

    outcome = pin_restart_only(startup, candidate)
    provider = outcome.config.model_providers["xingchen"]

    assert provider.type == "xingchen"
    assert provider.models == ["chat-pro"]
    assert provider.gateway_api_key == "gateway-key"
    assert provider.x_token == "complete.x.token"
    assert provider.device_id == "device-id"
    assert provider.install_id == "install-id"
    assert provider.app_version == "2.4.1"
    assert provider.route_target == "ops-gateway"
    assert provider.client_type == "desktop"
    assert provider.user_agent == "super-agent/1.0"
    assert provider.disabled_models == ["chat-lite"]
    reported = "\n".join(outcome.restart_required)
    assert "new-key" not in reported
    assert "new.x.token" not in reported
    assert "model_providers.xingchen.disabled_models" in outcome.restart_required
    assert "model_providers.xingchen.models" in outcome.restart_required


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


def test_the_listen_address_is_pinned_to_what_the_process_bound() -> None:
    # A port change is realised by starting a new process, so reporting the new one would lie.
    startup = ProxyConfig.model_validate({"server": {"host": "127.0.0.1", "port": 4142}})
    candidate = ProxyConfig.model_validate({"server": {"host": "0.0.0.0", "port": 9999}})
    outcome = pin_restart_only(startup, candidate)
    assert outcome.config.server.host == "127.0.0.1"
    assert outcome.config.server.port == 4142
    assert outcome.restart_required == ("server.host", "server.port")


def test_the_token_file_is_pinned_per_provider() -> None:
    startup = ProxyConfig.model_validate(
        {"model_providers": {"ghc": {"type": "github_copilot", "github_token_file": "/a"}}}
    )
    candidate = ProxyConfig.model_validate(
        {"model_providers": {"ghc": {"type": "github_copilot", "github_token_file": "/b"}}}
    )
    outcome = pin_restart_only(startup, candidate)
    ghc = outcome.config.model_providers["ghc"]
    assert isinstance(ghc, GithubCopilotProviderConfig)
    assert ghc.github_token_file == "/a"
    assert outcome.restart_required == ("model_providers.ghc.github_token_file",)


def test_tls_settings_stay_hot_reloadable() -> None:
    # Only the bind address is restart-only; the rest of `server` is not swept in with it.
    startup = ProxyConfig()
    candidate = ProxyConfig.model_validate({"server": {"tls": {"mode": "both"}}})
    outcome = pin_restart_only(startup, candidate)
    assert outcome.config.server.tls.mode == "both"
    assert outcome.restart_required == ()


def test_a_config_in_the_working_directory_is_not_consulted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Which directory the service was launched from does not decide what it runs.

    It did until 2026-08-22, inherited from the path this replaced. What that produced: the proxy started from a checkout of the sibling JS service picked up that project's `config.yaml`, and refused to start on a key the operator had never written for this one — a message naming a setting when the thing that was wrong was the file. Nothing had guarded the behaviour either way, so removing it needed a test more than keeping it did.
    """
    monkeypatch.delenv(CONFIG_PATH_VARIABLE, raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    launch_dir = tmp_path / "somebody-elses-checkout"
    launch_dir.mkdir()
    write_config(launch_dir, "server:\n  port: 4321\n")
    monkeypatch.chdir(launch_dir)

    assert resolve_config_path(None) is None
    assert load_proxy_config().server.port != 4321


def test_the_config_path_variable_is_not_read_as_a_setting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`GHC_API_PROXY_CONFIG` names the file; it is not one of the settings inside it.

    Left in the value layer it arrives as a top-level `config` key, and `ProxyConfig` forbids unknown ones — so pointing at a config file would refuse to start rather than select it.
    """
    config = tmp_path / "config.yaml"
    config.write_text("server:\n  port: 4321\n", encoding="utf-8")
    monkeypatch.setenv("GHC_API_PROXY_CONFIG", str(config))

    assert environment_values() == {}
    assert load_proxy_config().server.port == 4321


def test_the_github_token_variable_is_not_read_as_a_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`GHC_API_PROXY_GITHUB_TOKEN` is a credential, and it shares the settings prefix.

    Measured, not anticipated: setting it made every start-up die on `api_proxy_github_token — Extra inputs are not permitted`, which reads as a bad config file rather than as the token the operator just exported. `load_proxy_config` is asserted alongside `environment_values` because the filter is only worth anything if the config it feeds still validates.
    """
    monkeypatch.setenv(GITHUB_TOKEN_VARIABLE, "ghu_probe")

    assert environment_values() == {}
    assert load_proxy_config() is not None


def test_the_flat_port_spelling_reaches_the_server_section() -> None:
    """`GHC_API_PROXY_PORT` is the spelling the prefix invites, and it used to break start-up.

    Nesting is by `__`, so it arrived as a top-level `port` key and `ProxyConfig` forbids unknown ones. The operator got `port — Extra inputs are not permitted` and a service that would not start, from a variable named exactly what it looks like it should be. `config.example.yaml` uses this spelling when it names the pidfile, so it is going to be typed.
    """
    assert environment_values({"GHC_API_PROXY_PORT": "5000"}) == {"server": {"port": "5000"}}
    assert load_proxy_config(environ={"GHC_API_PROXY_PORT": "5000"}).server.port == 5000


def test_the_flat_host_spelling_travels_with_it() -> None:
    # Aliased alongside `port` rather than on its own merit: the two are set together, and aliasing one would leave the other as exactly the trap this removes.
    assert environment_values({"GHC_API_PROXY_HOST": "0.0.0.0"}) == {"server": {"host": "0.0.0.0"}}
    assert load_proxy_config(environ={"GHC_API_PROXY_HOST": "0.0.0.0"}).server.host == "0.0.0.0"


def test_the_nested_spelling_still_works_and_wins_over_the_alias() -> None:
    """Both spellings set at once resolves the same way every time.

    Merged in one pass the answer would depend on which name the environment yielded first, which is the kind of thing that reads as flaky rather than as a rule.
    """
    both = {"GHC_API_PROXY_PORT": "5000", "GHC_API_PROXY_SERVER__PORT": "5001"}
    assert load_proxy_config(environ=both).server.port == 5001
    assert load_proxy_config(environ={"GHC_API_PROXY_SERVER__PORT": "5001"}).server.port == 5001


def test_the_command_line_still_beats_the_flat_spelling() -> None:
    # The alias sits in the environment tier, so `--port` overrides it like any other variable.
    config = load_proxy_config(
        environ={"GHC_API_PROXY_PORT": "5000"}, cli_overrides={"server": {"port": 4242}}
    )
    assert config.server.port == 4242


def test_a_relative_path_in_the_config_resolves_from_the_config_not_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ruled by the user 2026-08-28, and asserted from a working directory deliberately unrelated to the file.

    Which directory a command was launched from should not decide where the service writes its token or looks for its certificate. `resolve_config_path` already refuses to let cwd choose *which* config is read; this is the same rule applied to what that config says.
    """
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    config_dir = tmp_path / "etc"
    config_dir.mkdir()
    config_path = write_config(
        config_dir,
        "model_providers:\n"
        "  ghc:\n"
        "    type: github_copilot\n"
        '    github_token_file: "tokens/github_token"\n'
        'pidfile_dir: "run"\n'
        "server:\n"
        "  tls:\n"
        '    cert: "certs/server.pem"\n'
        '    key: "certs/server.key"\n',
    )
    monkeypatch.chdir(elsewhere)

    config = load_proxy_config(config_path=config_path)
    ghc = config.model_providers["ghc"]

    assert isinstance(ghc, GithubCopilotProviderConfig)
    assert ghc.github_token_file == str(config_dir / "tokens" / "github_token")
    assert config.pidfile_dir == str(config_dir / "run")
    assert config.server.tls.cert == str(config_dir / "certs" / "server.pem")
    assert config.server.tls.key == str(config_dir / "certs" / "server.key")


def test_a_relative_auth_state_file_is_based_on_the_config_file_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`auth_state_file` is a credential path like `github_token_file`, so it follows the same rule."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    config_dir = tmp_path / "etc"
    config_dir.mkdir()
    config_path = write_config(
        config_dir,
        "model_providers:\n"
        "  cb:\n"
        "    type: codebuddy\n"
        '    auth_state_file: "auth/codebuddy.info"\n',
    )
    monkeypatch.chdir(elsewhere)

    config = load_proxy_config(config_path=config_path)

    cb = config.model_providers["cb"]
    assert isinstance(cb, CodebuddyProviderConfig)
    assert cb.auth_state_file == str(config_dir / "auth" / "codebuddy.info")


def test_an_absolute_or_expandable_path_is_left_where_it_points(tmp_path: Path) -> None:
    """Rebasing applies to what is still relative after expansion, and to nothing else.

    `~` and `$XDG_DATA_HOME/ghc-api-proxy` already name absolute locations; joining them to the config's directory would move files the operator addressed unambiguously.
    """
    config_path = write_config(
        tmp_path,
        "model_providers:\n"
        "  ghc:\n"
        "    type: github_copilot\n"
        '    github_token_file: "/var/lib/ghc/token"\n'
        'pidfile_dir: "~/run"\n',
    )

    config = load_proxy_config(config_path=config_path)
    ghc = config.model_providers["ghc"]

    assert isinstance(ghc, GithubCopilotProviderConfig)
    assert ghc.github_token_file == "/var/lib/ghc/token"
    assert config.pidfile_dir == str(Path.home() / "run")


def test_a_relative_path_from_the_environment_keeps_shell_semantics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the file layer is rebased.

    Someone exporting a relative path, or typing one as an option, means the directory they are standing in. Resolving that against a config file somewhere else would be the ambush this rule exists to remove, pointed the other way.
    """
    config_dir = tmp_path / "etc"
    config_dir.mkdir()
    config_path = write_config(config_dir, "server:\n  port: 4141\n")
    monkeypatch.setenv(CONFIG_PATH_VARIABLE, str(config_path))

    from_environment = load_proxy_config(environ={"GHC_API_PROXY_PIDFILE_DIR": "run"})
    from_cli = load_proxy_config(cli_overrides={"pidfile_dir": "run"})

    assert from_environment.pidfile_dir == "run"
    assert from_cli.pidfile_dir == "run"
