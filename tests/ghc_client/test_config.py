import pytest

from app.ghc_client import GhcClientConfig, resolve_base_url


@pytest.mark.parametrize(
    ("account_type", "expected"),
    [
        ("individual", "https://api.githubcopilot.com"),
        ("business", "https://api.business.githubcopilot.com"),
        ("enterprise", "https://api.enterprise.githubcopilot.com"),
    ],
)
def test_base_url_follows_account_type(account_type: str, expected: str) -> None:
    config = GhcClientConfig(account_type=account_type)  # pyright: ignore[reportArgumentType]
    assert resolve_base_url(config) == expected
    assert config.base_url == expected


def test_override_wins_over_account_type_and_drops_trailing_slash() -> None:
    config = GhcClientConfig(
        account_type="enterprise",
        base_url_override="https://copilot.example/api/",
    )
    assert config.base_url == "https://copilot.example/api"


def test_empty_override_falls_back_to_account_type() -> None:
    config = GhcClientConfig(account_type="business", base_url_override="")
    assert config.base_url == "https://api.business.githubcopilot.com"
