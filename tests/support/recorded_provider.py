"""A model provider backed by a recording of what upstream actually said.

This is the stand-in tests ask for when they want the real thing without the network: a genuine
`GithubCopilotProvider`, over the real SDKs, over a transport that answers from a cassette. Nothing
about the provider or the client is faked, so everything below the recording — token exchange,
catalog parsing, SSE framing, block assembly — runs exactly as it does in production.

The distinction matters. A hand-written stand-in encodes what we *believe* upstream does, and it
was that belief which hid a defect: real Copilot sends a different `item.id` on `output_item.added`
and `output_item.done`, no fake ever did, and streaming on the primary path returned zero bytes.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.config.schema import ModelProviderConfig, ProxyConfig
from app.ghc_client import CopilotTokenManager, GhcApiClient, GhcClientConfig
from app.model_provider import GithubCopilotProvider, ModelProvider
from app.server.composition import Chain, build_chain
from support.cassettes import Cassette, ReplayTransport

CASSETTE_DIR = Path(__file__).resolve().parents[1] / "cassettes"
BASE_URL = "https://api.githubcopilot.com"


class RecordedTokenSource:
    """Stands in for the stored GitHub token, which never reaches a cassette."""

    async def get_token(self) -> str:
        return "gh-token-from-test"

    async def refresh(self) -> str | None:
        return None


def cassette_path(name: str) -> Path:
    return CASSETTE_DIR / f"{name}.json"


def replay_client(name: str) -> httpx.AsyncClient:
    """An httpx client that answers from the named cassette and never reaches the network."""
    return httpx.AsyncClient(transport=ReplayTransport(Cassette.read(cassette_path(name))))


def recorded_provider(name: str, http_client: httpx.AsyncClient) -> GithubCopilotProvider:
    """A real provider whose upstream is the recording.

    Built the way `composition.build_copilot_provider` builds it, minus the credential: the token
    exchange is itself in the cassette, so the manager runs its real code path against a recorded
    answer rather than being replaced.
    """
    ghc_config = GhcClientConfig(base_url_override=BASE_URL)
    client = GhcApiClient(
        AsyncOpenAI(
            api_key="proxy-managed", base_url=BASE_URL, http_client=http_client, max_retries=0
        ),
        AsyncAnthropic(
            api_key="proxy-managed", base_url=BASE_URL, http_client=http_client, max_retries=0
        ),
        CopilotTokenManager(RecordedTokenSource(), http_client),
        ghc_config,
        interaction_id="interaction",
    )
    return GithubCopilotProvider(
        "ghc",
        client,
        ModelProviderConfig(type="github_copilot", base_url=BASE_URL),
        http_client=http_client,
        base_url=BASE_URL,
    )


@asynccontextmanager
async def recorded_chain(name: str) -> AsyncGenerator[Chain]:
    """A whole chain served by the recording, closed on the way out."""
    http_client = replay_client(name)
    try:
        provider = recorded_provider(name, http_client)
        providers: dict[str, ModelProvider] = {"ghc": provider}
        config = ProxyConfig.model_validate(
            {
                "model_providers": {"ghc": {"type": "github_copilot", "base_url": BASE_URL}},
                "default_model_provider": "ghc",
            }
        )
        yield build_chain(config, http_client=http_client, providers=providers)
    finally:
        await http_client.aclose()
