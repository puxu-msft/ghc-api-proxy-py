"""Copilot upstream adapter.

The actual Copilot API access lives in the standalone `app.ghc_client` library.
This module maps `AppSettings` onto the library config.
It adapts `GitHubTokenManager` to the library's token source protocol.
It wraps the library client as this project's `UpstreamTarget`.
"""

from collections.abc import Mapping
from typing import Any

import httpx2

from app.config.settings import AppSettings
from app.ghc_client import (
    GhcApiClient,
    build_identity_headers,
    build_request_headers,
)
from app.ghc_client.auth.providers import GitHubTokenManager
from app.ghc_client.tokens import CopilotTokenManager
from app.upstream.client import SDKClients
from app.upstream.ghc_settings import ghc_config_from_settings


class GitHubTokenSourceAdapter:
    """Adapts `GitHubTokenManager` to the `GitHubTokenSource` protocol of `app.ghc_client`.

    The library only needs the token string, not this project's `TokenInfo` or provider chain.
    """

    def __init__(self, manager: GitHubTokenManager) -> None:
        self._manager = manager

    async def get_token(self) -> str:
        info = await self._manager.get_token()
        return info.token

    async def refresh(self) -> str | None:
        refreshed = await self._manager.refresh()
        return refreshed.token if refreshed is not None else None


def build_copilot_identity_headers(settings: AppSettings) -> dict[str, str]:
    return build_identity_headers(ghc_config_from_settings(settings))


def build_copilot_headers(
    token: str,
    settings: AppSettings,
    *,
    interaction_id: str,
    request_id: str | None = None,
    intent: str = "conversation-panel",
    vision: bool = False,
    model_request_headers: Mapping[str, str] | None = None,
) -> dict[str, str]:
    return build_request_headers(
        token,
        ghc_config_from_settings(settings),
        interaction_id=interaction_id,
        request_id=request_id,
        intent=intent,
        vision=vision,
        model_request_headers=model_request_headers,
    )


class CopilotUpstream:
    """Exposes `GhcApiClient` in the shape of `UpstreamTarget`.

    `UpstreamTarget` names protocol families; the library names endpoints.
    This class is the single translation point between the two.
    """

    def __init__(
        self,
        clients: SDKClients,
        token_manager: CopilotTokenManager,
        settings: AppSettings,
        *,
        interaction_id: str,
    ) -> None:
        self._client = GhcApiClient(
            clients.openai,
            clients.anthropic,
            token_manager,
            ghc_config_from_settings(settings),
            interaction_id=interaction_id,
        )

    async def send_openai(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx2.Response:
        return await self._client.send_chat_completions(payload, stream=stream)

    async def send_anthropic(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        return await self._client.send_anthropic_messages(
            payload,
            stream=stream,
            extra_headers=extra_headers,
        )

    async def send_anthropic_count_tokens(
        self,
        payload: Mapping[str, Any],
    ) -> httpx2.Response:
        return await self._client.send_anthropic_count_tokens(payload)

    async def send_responses(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx2.Response:
        return await self._client.send_responses(payload, stream=stream)

    async def send_responses_headers(
        self,
        payload: Mapping[str, Any],
    ) -> httpx2.Response:
        return await self._client.send_responses_headers(payload)

    async def send_embeddings(
        self,
        payload: Mapping[str, Any],
    ) -> httpx2.Response:
        return await self._client.send_embeddings(payload)
