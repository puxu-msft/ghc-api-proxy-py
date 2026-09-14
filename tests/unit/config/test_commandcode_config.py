import pytest
from pydantic import ValidationError

from app.config.schema import CommandCodeProviderConfig, ProxyConfig


def test_commandcode_provider_has_protocol_defaults_and_redacts_api_key() -> None:
    provider = CommandCodeProviderConfig.model_validate(
        {"type": "commandcode", "api_key": "user_test"}
    )

    assert provider.api_base_url == "https://api.commandcode.ai"
    assert provider.project_slug == "cc-proxy"
    assert provider.initialize_upstream is True
    assert provider.empty_system_placeholder is True
    assert "user_test" not in repr(provider)


@pytest.mark.parametrize(
    "raw",
    [
        {"type": "commandcode", "api_key": ""},
        {"type": "commandcode", "api_key": "user_test", "api_base_url": "localhost"},
        {
            "type": "commandcode",
            "api_key": "user_test",
            "models": ["m", "M"],
        },
    ],
)
def test_commandcode_provider_rejects_invalid_static_configuration(
    raw: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        CommandCodeProviderConfig.model_validate(raw)


def test_commandcode_provider_is_part_of_the_discriminated_proxy_config() -> None:
    config = ProxyConfig.model_validate(
        {
            "model_providers": {
                "cc": {"type": "commandcode", "api_key": "user_test"}
            },
            "default_model_provider": "cc",
        }
    )

    assert config.model_providers["cc"].type == "commandcode"
