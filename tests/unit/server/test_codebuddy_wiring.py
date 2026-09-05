"""Wiring a CodeBuddy provider through the composition root.

The assertions are about what a configuration *produces*: the provider type the
registry holds, the base URL it reports, and that both providers get their own
client. Built through `build_chain` rather than by constructing providers
directly, because the wiring — one client per provider, one credential chain per
provider — is the thing under test.
"""

from pathlib import Path

import httpx2
import pytest
from pydantic import ValidationError

from app.config.schema import ProxyConfig
from app.model_provider import CODEBUDDY_PROVIDER_TYPE, CodebuddyProvider, GithubCopilotProvider
from app.model_provider.codebuddy_client.models import DEFAULT_MODEL_IDS
from app.server.composition import build_chain


def mixed_config(token_file: Path) -> ProxyConfig:
    return ProxyConfig.model_validate(
        {
            "model_providers": {
                "ghc": {
                    "type": "github_copilot",
                    "api_base_url": "https://api.githubcopilot.com",
                    "github_token_file": str(token_file),
                },
                "cb": {"type": "codebuddy"},
            },
            "default_model_provider": "ghc",
        }
    )


@pytest.mark.asyncio
async def test_a_codebuddy_entry_builds_a_codebuddy_provider() -> None:
    config = ProxyConfig.model_validate(
        {"model_providers": {"cb": {"type": CODEBUDDY_PROVIDER_TYPE}}}
    )
    http_client = httpx2.AsyncClient()
    chain = build_chain(config, http_client=http_client)
    try:
        provider = chain.providers.get("cb")
        assert isinstance(provider, CodebuddyProvider)
        assert provider.available_ids == frozenset(DEFAULT_MODEL_IDS)
        # The constant, not the config's empty string: `base_url` is what
        # `/api/status` prints, and printing an empty URL would report nothing.
        assert provider.base_url == "https://copilot.tencent.com"
        assert chain.providers.default_name == "cb"
    finally:
        await chain.aclose()
        await http_client.aclose()


@pytest.mark.asyncio
async def test_a_mixed_config_builds_both_types_with_their_own_clients(
    tmp_path: Path,
) -> None:
    config = mixed_config(tmp_path / "absent-token")
    http_client = httpx2.AsyncClient()
    chain = build_chain(config, http_client=http_client)
    try:
        assert isinstance(chain.providers.get("ghc"), GithubCopilotProvider)
        assert isinstance(chain.providers.get("cb"), CodebuddyProvider)
        # One client per provider: the copilot one and the codebuddy one must not
        # share a pool, whatever their base hosts turn out to be.
        assert set(chain.provider_clients) == {"ghc", "cb"}
    finally:
        await chain.aclose()
        await http_client.aclose()


def test_an_unknown_provider_type_is_rejected_by_the_schema() -> None:
    with pytest.raises(ValidationError):
        ProxyConfig.model_validate(
            {
                "model_providers": {
                    "weird": {"type": "not-a-type"},
                }
            }
        )
