"""Configuration for the CodeBuddy client library.

Deliberately not the host's `ModelProviderConfig`, for the same reason `GhcClientConfig`
is not: a library should not know the host's config model.
"""

from dataclasses import dataclass

# Measured from the reference converter (`refs/codebuddy2api/converter.py`), which has
# served this host: one backend, one inference path (`/v2/chat/completions`), no
# separate auth host — the refresh endpoint lives on the same origin.
CODEBUDDY_API_BASE_URL = "https://copilot.tencent.com"
# Sent when the login state does not name one. The reference ships the same default.
DEFAULT_DOMAIN = "www.codebuddy.cn"
USER_AGENT = "ghc-api-proxy-codebuddy/1.0"


@dataclass(frozen=True, slots=True)
class CodebuddyClientConfig:
    """All configuration this library accepts."""

    api_base_url_override: str = ""
    user_agent: str = USER_AGENT

    @property
    def api_base_url(self) -> str:
        return (self.api_base_url_override or CODEBUDDY_API_BASE_URL).rstrip("/")
