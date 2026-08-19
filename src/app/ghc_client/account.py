from collections.abc import Mapping

import httpx

from app.ghc_client.config import GITHUB_AUTH_BASE_URL

USER_PATH = "/user"
COPILOT_USER_PATH = "/copilot_internal/user"
GITHUB_API_VERSION = "2022-11-28"
COPILOT_INTERNAL_API_VERSION = "2025-04-01"


def infer_account_type(usage: Mapping[str, object]) -> str | None:
    haystack = f"{usage.get('copilot_plan', '')} {usage.get('access_type_sku', '')}".lower()
    if "enterprise" in haystack:
        return "enterprise"
    if "business" in haystack:
        return "business"
    if any(marker in haystack for marker in ("individual", "free", "pro")):
        return "individual"
    return None


class GitHubAccountClient:
    """Read-only GitHub REST endpoints describing the Copilot subscription.

    Used only to infer the account type, which selects the API base URL.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        auth_base_url: str = GITHUB_AUTH_BASE_URL,
    ) -> None:
        self._http = http_client
        self._auth_base_url = auth_base_url.rstrip("/")

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"token {token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }

    async def get_user(self, token: str) -> dict[str, object]:
        response = await self._http.get(
            f"{self._auth_base_url}{USER_PATH}",
            headers=self._headers(token),
        )
        response.raise_for_status()
        data: dict[str, object] = response.json()
        return data

    async def get_copilot_usage(self, token: str) -> dict[str, object]:
        headers = self._headers(token)
        headers["X-GitHub-Api-Version"] = COPILOT_INTERNAL_API_VERSION
        response = await self._http.get(
            f"{self._auth_base_url}{COPILOT_USER_PATH}",
            headers=headers,
        )
        response.raise_for_status()
        data: dict[str, object] = response.json()
        return data
