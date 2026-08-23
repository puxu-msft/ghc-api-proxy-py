"""Copilot upstream adapter.

The actual Copilot API access lives in the standalone `app.model_provider.ghc_client` library.
This module maps `AppSettings` onto the library config, and adapts `GitHubTokenManager` to the library's token source protocol.

It used to also wrap the library client as this project's `UpstreamTarget`. That class went to `src/.archived/app/upstream/copilot_upstream.py` on 2026-08-23: `UpstreamTarget` had already been archived, nothing instantiated the wrapper, and the live provider reaches `GhcApiClient` through `app/model_provider/github_copilot.py` instead.
"""

from collections.abc import Mapping

from app.config.settings import AppSettings
from app.model_provider.ghc_client import (
    build_identity_headers,
    build_request_headers,
)
from app.model_provider.ghc_client.auth.providers import GitHubTokenManager
from app.upstream.ghc_settings import ghc_config_from_settings


class GitHubTokenSourceAdapter:
    """Adapts `GitHubTokenManager` to the `GitHubTokenSource` protocol of `app.model_provider.ghc_client`.

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
