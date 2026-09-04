from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.config.schema import (
    NOT_HOT_RELOADABLE,
    GithubCopilotProviderConfig,
    ProxyConfig,
    XingchenProviderConfig,
)
from app.pipeline.model_resolution import QUALIFIER_SEPARATOR, canonical

SPEC_PATH = Path(__file__).resolve().parents[3] / "docs/.human-controlled/config.example.yaml"


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
    assert config.upstream_request_retry.strategies.network.max_retries == 9
    assert config.hooks.on_client_request_parsed == []
    assert config.history.enabled is True


def test_defaults_disable_the_upstream_silence_terminators() -> None:
    # The spec's frozen invariant: never false-kill legitimate thinking.
    # Both phase-scoped terminators default to off; only the whole-attempt deadline bounds it.
    config = ProxyConfig()
    assert config.upstream_request_timeouts.response_header == 0
    assert config.upstream_request_timeouts.stream_idle == 0
    assert config.upstream_request_timeouts.upstream_request_deadline == 1200


@pytest.mark.parametrize("name", ["A/B", "", "   "])
def test_a_provider_name_the_qualifier_syntax_cannot_address_is_refused(name: str) -> None:
    """Spec §2.1 and §5.1.2. Both shapes load as configuration, and neither can be routed to.

    `A/B` written into a qualifier as `A/B/model` splits on the **first** separator, so it reads as the unknown provider `A` and takes the fallback path — the provider exists, starts, serves as the default, and is unreachable by every qualifier that names it.

    An empty name inverts §5.1.2 instead: `/model` has an empty head, which is *defined* to mean an unrecognised provider so that a dropped name lands on the fallback. Configure a provider called `""` and that safety net becomes a hit.
    """
    with pytest.raises(ValidationError):
        ProxyConfig.model_validate({"model_providers": {name: {"type": "github_copilot"}}})


def test_an_ordinary_provider_name_is_still_accepted() -> None:
    """The control for the check above, which is otherwise satisfied by refusing every name."""
    config = ProxyConfig.model_validate({"model_providers": {"ghc": {"type": "github_copilot"}}})
    assert "ghc" in config.model_providers


def xingchen_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "type": "xingchen",
        "models": ["chat-pro", "chat-lite"],
        "gateway_api_key": "gateway-secret",
        "x_token": "complete.x.token",
        "device_id": "device-id",
        "install_id": "install-id",
    }
    values.update(overrides)
    return values


def test_provider_config_is_discriminated_by_type() -> None:
    config = ProxyConfig.model_validate(
        {
            "model_providers": {
                "ghc": {"type": "github_copilot"},
                "xingchen": xingchen_values(),
            },
            "default_model_provider": "ghc",
        }
    )

    ghc = config.model_providers["ghc"]
    xingchen = config.model_providers["xingchen"]
    assert isinstance(ghc, GithubCopilotProviderConfig)
    assert isinstance(xingchen, XingchenProviderConfig)
    assert xingchen.api_base_url == "https://agent.teleai.com.cn/superCowork/sapi/api/v1"
    assert xingchen.app_version == "2.4.1"
    assert xingchen.route_target == "ops-gateway"
    assert xingchen.client_type == "desktop"
    assert xingchen.user_agent == "super-agent/1.0"
    assert "gateway-secret" not in repr(xingchen)
    assert "complete.x.token" not in repr(xingchen)


@pytest.mark.parametrize(
    "missing",
    ["models", "gateway_api_key", "x_token", "device_id", "install_id"],
)
def test_xingchen_rejects_a_missing_required_field(missing: str) -> None:
    values = xingchen_values()
    del values[missing]
    with pytest.raises(ValidationError):
        ProxyConfig.model_validate({"model_providers": {"xingchen": values}})


@pytest.mark.parametrize(
    "field",
    [
        "api_base_url",
        "gateway_api_key",
        "x_token",
        "device_id",
        "install_id",
        "app_version",
        "route_target",
        "client_type",
        "user_agent",
    ],
)
def test_xingchen_rejects_blank_identity_and_credential_values(field: str) -> None:
    with pytest.raises(ValidationError):
        ProxyConfig.model_validate(
            {"model_providers": {"xingchen": xingchen_values(**{field: "  "})}}
        )


@pytest.mark.parametrize("models", [[], ["chat-pro", ""], ["chat-pro", "  "], ["chat-pro", "chat-pro"]])
def test_xingchen_rejects_empty_blank_or_duplicate_models(models: list[str]) -> None:
    with pytest.raises(ValidationError):
        ProxyConfig.model_validate(
            {"model_providers": {"xingchen": xingchen_values(models=models)}}
        )


@pytest.mark.parametrize(
    ("first", "second"),
    [("m-1.0", "m-1-0"), ("Chat-Pro", "chat-pro")],
)
def test_xingchen_rejects_model_ids_routing_treats_as_equivalent(
    first: str,
    second: str,
) -> None:
    assert canonical(first) == canonical(second)
    with pytest.raises(ValidationError, match="canonically equivalent"):
        ProxyConfig.model_validate(
            {
                "model_providers": {
                    "xingchen": xingchen_values(models=[first, second])
                }
            }
        )


def test_xingchen_validation_errors_hide_credential_inputs() -> None:
    values = xingchen_values(gateway_api_key="LEAK-GATEWAY", x_token="LEAK.X.TOKEN")
    del values["install_id"]

    with pytest.raises(ValidationError) as raised:
        ProxyConfig.model_validate({"model_providers": {"xingchen": values}})

    rendered = str(raised.value)
    assert "LEAK-GATEWAY" not in rendered
    assert "LEAK.X.TOKEN" not in rendered
    assert "model_providers.xingchen.xingchen.install_id" in rendered
    assert "Field required" in rendered


def test_provider_variants_reject_each_others_fields() -> None:
    with pytest.raises(ValidationError):
        ProxyConfig.model_validate(
            {
                "model_providers": {
                    "xingchen": xingchen_values(github_token_file="not-for-xingchen")
                }
            }
        )
    with pytest.raises(ValidationError):
        ProxyConfig.model_validate(
            {
                "model_providers": {
                    "ghc": {"type": "github_copilot", "x_token": "not-for-github"}
                }
            }
        )


def test_the_qualifier_separator_matches_the_config_boundary() -> None:
    """`schema.py` writes `/` literally rather than importing it, so the config layer does not depend on the pipeline.

    That makes it a transcription of `QUALIFIER_SEPARATOR`, and a transcription is a thing that can silently fall behind while both sides keep passing their own tests. This is what notices.
    """
    assert QUALIFIER_SEPARATOR == "/"


def test_a_counting_leg_may_name_any_configured_provider() -> None:
    """`ghc` is legal because a provider is called `ghc`, not because the string is special.

    The field spent a while typed `Literal["ghc", "local"]`, which said that only a deployment whose provider happens to carry that name may ask upstream for a count. Nobody made that rule. A deployment naming its providers `A` and `B` must be able to say so here.
    """
    config = ProxyConfig.model_validate(
        {
            "model_providers": {"A": {"type": "github_copilot"}, "B": {"type": "github_copilot"}},
            "default_model_provider": "A",
            "inbound": {"anthropic_count_tokens": {"providers": ["B", "local"]}},
        }
    )
    assert config.inbound.anthropic_count_tokens.providers == ["B", "local"]


def test_a_counting_leg_naming_no_configured_provider_is_refused() -> None:
    """The other half: the check is against **this** configuration, not against a fixed list.

    `ghc` is exactly as wrong here as `typo` would be, because this deployment configures neither.
    """
    with pytest.raises(ValidationError) as raised:
        ProxyConfig.model_validate(
            {
                "model_providers": {"A": {"type": "github_copilot"}},
                "default_model_provider": "A",
                "inbound": {"anthropic_count_tokens": {"providers": ["ghc", "local"]}},
            }
        )
    assert "'ghc'" in str(raised.value)


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
