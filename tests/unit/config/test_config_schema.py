from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.config.schema import NOT_HOT_RELOADABLE, ProxyConfig

SPEC_PATH = Path(__file__).resolve().parents[2] / "docs/.human-controlled/config.example.yaml"


@pytest.mark.skipif(not SPEC_PATH.is_file(), reason="authoritative config spec not present")
def test_authoritative_example_config_parses() -> None:
    # The spec file is the oracle.
    # extra="forbid" means any active key we failed to model fails here, not at startup.
    raw = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    config = ProxyConfig.model_validate(raw)

    assert config.server.tls.mode == "both"
    assert config.server.host == "127.0.0.1"
    assert config.server.port == 4142
    assert config.default_model_provider == "ghc"
    assert config.model_providers["ghc"].type == "github_copilot"
    assert config.model_providers["ghc"].github_token_file.endswith("github_token.txt")
    assert config.model_mappings["opus"] == "claude-opus-5"
    assert config.upstream_request_timeouts.upstream_request_deadline == 1200
    assert config.client_delivery.client_request_deadline == 3600
    assert config.upstream_request_retry.strategies.continuation.enabled is True
    assert config.hooks.on_client_request_parsed == []
    assert config.history.enabled is True


def test_defaults_disable_the_upstream_silence_terminators() -> None:
    # The spec's frozen invariant: never false-kill legitimate thinking.
    # Both phase-scoped terminators default to off; only the whole-attempt deadline bounds it.
    config = ProxyConfig()
    assert config.upstream_request_timeouts.response_header == 0
    assert config.upstream_request_timeouts.stream_idle == 0
    assert config.upstream_request_timeouts.upstream_request_deadline == 1200


def test_model_mappings_have_no_built_in_defaults() -> None:
    # The spec makes model_mappings the sole source of mapping.
    # A built-in default would silently resolve a name the operator never configured.
    assert ProxyConfig().model_mappings == {}


@pytest.mark.parametrize("value", [True, False, "both"])
def test_tls_mode_accepts_the_three_states(value: bool | str) -> None:
    config = ProxyConfig.model_validate({"server": {"tls": {"mode": value}}})
    assert config.server.tls.mode == value


def test_yaml_off_reaches_context_editing_as_a_bool() -> None:
    # YAML 1.1 parses a bare `off` as boolean false.
    # The disabled state must accept a bool, not the literal string the comment shows.
    raw = yaml.safe_load("hook_fix_anthropic_request:\n  context_editing:\n    enabled: off\n")
    config = ProxyConfig.model_validate(raw)
    assert config.hook_fix_anthropic_request.context_editing.enabled is False


def test_context_editing_accepts_the_named_modes() -> None:
    config = ProxyConfig.model_validate(
        {"hook_fix_anthropic_request": {"context_editing": {"enabled": "clear-both"}}}
    )
    assert config.hook_fix_anthropic_request.context_editing.enabled == "clear-both"


def test_assistant_message_layout_accepts_false_as_passthrough() -> None:
    config = ProxyConfig.model_validate(
        {"hook_fix_anthropic_request": {"thinking": {"assistant_message_layout": False}}}
    )
    assert config.hook_fix_anthropic_request.thinking.assistant_message_layout is False


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProxyConfig.model_validate({"no_such_section": {}})


def test_unknown_key_inside_a_section_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProxyConfig.model_validate({"client_delivery": {"no_such_field": 1}})


def test_snapshot_is_frozen() -> None:
    config = ProxyConfig()
    with pytest.raises(ValidationError):
        config.graceful_cleanup_timeout = 1  # pyright: ignore[reportAttributeAccessIssue]


def test_restart_only_paths_are_recorded() -> None:
    assert "proxy" in NOT_HOT_RELOADABLE
    assert "reactive_rate_limiter" in NOT_HOT_RELOADABLE
    assert "upstream_request_retry.max_total" in NOT_HOT_RELOADABLE


def test_the_listen_address_is_restart_only() -> None:
    # Nothing rebinds a live listener, so `current` would otherwise report a port nobody serves.
    assert "server.host" in NOT_HOT_RELOADABLE
    assert "server.port" in NOT_HOT_RELOADABLE
