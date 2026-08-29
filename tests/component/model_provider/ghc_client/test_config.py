import pytest

from app.model_provider.ghc_client import (
    GhcClientConfig,
    resolve_api_base_url,
    resolve_github_web_base_url,
)


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
    assert resolve_api_base_url(config) == expected
    assert config.api_base_url == expected


def test_override_wins_over_account_type_and_drops_trailing_slash() -> None:
    config = GhcClientConfig(
        account_type="enterprise",
        api_base_url_override="https://copilot.example/api/",
    )
    assert config.api_base_url == "https://copilot.example/api"


def test_empty_override_falls_back_to_account_type() -> None:
    config = GhcClientConfig(account_type="business", api_base_url_override="")
    assert config.api_base_url == "https://api.business.githubcopilot.com"


def test_self_hosted_uses_the_configured_host() -> None:
    config = GhcClientConfig(
        account_type="self-hosted",
        api_base_url_override="https://msft.ghe.com",
    )
    assert config.api_base_url == "https://msft.ghe.com"


def test_self_hosted_without_a_host_is_rejected() -> None:
    # A self-hosted host cannot be derived from the account type, unlike the three hosted tiers.
    config = GhcClientConfig(account_type="self-hosted")
    with pytest.raises(ValueError, match="self-hosted"):
        resolve_api_base_url(config)


@pytest.mark.parametrize(
    ("auth_base_url", "expected"),
    [
        ("https://api.github.com", "https://github.com"),
        ("https://api.github.com/", "https://github.com"),
        # Any number of trailing slashes normalises away; every other path is refused below.
        ("https://api.github.com//", "https://github.com"),
        ("https://api.octocorp.ghe.com", "https://octocorp.ghe.com"),
        ("https://api.octocorp.ghe.com:443", "https://octocorp.ghe.com"),
        # A multi-label tenant is allowed deliberately: public documentation shows only one label, which is not the same as showing that two are illegal.
        ("https://api.eu-west.octocorp.ghe.com", "https://eu-west.octocorp.ghe.com"),
        # Self-hosted Enterprise Server: the REST API hangs off the browser's own host under `/api/v3`, so that host is the OAuth origin. The path is what tells this form apart from the two above.
        ("https://ghe.example.com/api/v3", "https://ghe.example.com"),
        ("https://ghe.example.com/api/v3/", "https://ghe.example.com"),
        ("https://ghe.example.com:443/api/v3", "https://ghe.example.com"),
    ],
)
def test_web_base_url_is_derived_from_the_auth_host(auth_base_url: str, expected: str) -> None:
    assert resolve_github_web_base_url(auth_base_url) == expected
    assert GhcClientConfig(auth_base_url_override=auth_base_url).github_web_base_url == expected


def test_the_default_auth_host_still_derives_dotcom() -> None:
    """The unconfigured deployment must land on exactly the origin this code used before it was derivable."""
    assert GhcClientConfig().github_web_base_url == "https://github.com"


@pytest.mark.parametrize(
    "auth_base_url",
    [
        # Two hosts nothing can map: a local stand-in (a legal `auth_base_url`, see the field's docstring) and an unrelated enterprise host.
        "http://127.0.0.1:8080",
        "https://github.example.com",
        # `.ghe.com` with no tenant at all, and with an empty label where the tenant belongs. The second derived `https://.ghe.com` while the check only compared the whole string against `ghe.com`.
        "https://api.ghe.com",
        "https://api..ghe.com",
        "https://api.foo..ghe.com",
        # Shapes that would silently change which URL is posted to.
        "https://api.github.com/enterprise",
        "https://user:pw@api.github.com",
        "https://api.github.com?next=x",
        "https://api.github.com#frag",
        "https://api.octocorp.ghe.com:8443",
        # `api.` is required: the auth host is the API host, and treating a bare tenant as one would map it to itself.
        "https://octocorp.ghe.com",
        # `/api/v3` exactly, or no path at all. A neighbouring version or a prefix of it is not an Enterprise Server REST root, and guessing that it is would post device codes at a host nobody named.
        "https://ghe.example.com/api/v4",
        "https://ghe.example.com/api",
        "https://ghe.example.com/api/v3/extra",
        # Userinfo that is *present* but empty. A per-field truthiness check reads these as absent and lets them through, which is why the check compares the whole input against the origin it rebuilds.
        "https://@api.github.com",
        "https://:@api.github.com",
        # Empty delimiters, same shape: the component carries no value but the authority is no longer a bare origin.
        "https://api.github.com?",
        "https://api.github.com#",
        "https://api.github.com:",
        # Shapes where `urlsplit` raises first, with wording of its own that names neither what arrived nor what was wanted.
        "https://api.octocorp.ghe.com:not-a-port",
        "https://[bad",
    ],
)
def test_a_host_no_mapping_covers_is_refused_rather_than_sent_to_dotcom(auth_base_url: str) -> None:
    """Refusal, never a fallback, and always in this function's own words.

    Falling back to github.com is the defect this derivation exists to remove: a device code issued by the wrong tenant produces a token the provider's upstream rejects, from a login that reported success. Every refusal has to name both what arrived and what was expected, including the ones the URL parser raises on its own. Spec §3.2, §3.3.
    """
    with pytest.raises(ValueError, match="Device Flow OAuth origin") as raised:
        resolve_github_web_base_url(auth_base_url)
    assert repr(auth_base_url) in str(raised.value)
