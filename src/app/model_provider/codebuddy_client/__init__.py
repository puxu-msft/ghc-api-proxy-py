"""The CodeBuddy client library, sibling of `ghc_client`.

Where `ghc_client` wraps the OpenAI and Anthropic SDKs pointed at GitHub Copilot,
this one speaks raw `httpx2` to the Tencent CodeBuddy backend: one inference
endpoint, desktop-file authentication, a static catalog. The pipeline meets both
through the `ModelProvider` protocol and cannot tell them apart, which is the point.
"""

from app.model_provider.codebuddy_client.auth_state import (
    AuthRefreshFailed,
    AuthStateInvalid,
    AuthStateMissing,
    CodebuddyCredentials,
    DesktopAuthState,
    discover_auth_file,
)
from app.model_provider.codebuddy_client.client import CodebuddyClient
from app.model_provider.codebuddy_client.config import CodebuddyClientConfig
from app.model_provider.codebuddy_client.models import static_catalog

__all__ = [
    "AuthRefreshFailed",
    "AuthStateInvalid",
    "AuthStateMissing",
    "CodebuddyClient",
    "CodebuddyClientConfig",
    "CodebuddyCredentials",
    "DesktopAuthState",
    "discover_auth_file",
    "static_catalog",
]
