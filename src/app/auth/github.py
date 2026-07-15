from collections.abc import Mapping
from typing import Any

import httpx

GITHUB_API_BASE_URL = "https://api.github.com"
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


class GitHubClient:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"token {token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }

    async def get_user(self, token: str) -> dict[str, Any]:
        response = await self._http.get(
            f"{GITHUB_API_BASE_URL}/user",
            headers=self._headers(token),
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    async def get_copilot_usage(self, token: str) -> dict[str, Any]:
        headers = self._headers(token)
        headers["X-GitHub-Api-Version"] = COPILOT_INTERNAL_API_VERSION
        response = await self._http.get(
            f"{GITHUB_API_BASE_URL}/copilot_internal/user",
            headers=headers,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data