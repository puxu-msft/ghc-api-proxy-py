"""Standalone GitHub Copilot API client library.

Imports nothing from `app.*`; depends only on stdlib, httpx and the openai/anthropic SDKs.
Callers supply `GhcClientConfig` and `GitHubTokenSource`.
The model catalog is returned as raw wire data for the caller to validate with its own types.

In scope: token exchange, account probing, model catalog fetch, model-agnostic request building.
Out of scope: model name resolution, body translation, history, retry orchestration.
"""

from app.ghc_client.account import GitHubAccountClient, infer_account_type
from app.ghc_client.client import GhcApiClient
from app.ghc_client.config import GhcClientConfig, resolve_base_url
from app.ghc_client.device_flow import (
    DeviceCode,
    DeviceFlowClient,
    DeviceFlowError,
)
from app.ghc_client.headers import build_identity_headers, build_request_headers
from app.ghc_client.models import ModelCatalogPage, fetch_models
from app.ghc_client.tokens import (
    CopilotTokenInfo,
    CopilotTokenManager,
    GitHubTokenSource,
)
from app.ghc_client.transport import (
    ResponsesHeadersPendingTransportError,
    is_responses_headers_pending_transport_error,
)

__all__ = [
    "CopilotTokenInfo",
    "CopilotTokenManager",
    "DeviceCode",
    "DeviceFlowClient",
    "DeviceFlowError",
    "GhcApiClient",
    "GhcClientConfig",
    "GitHubAccountClient",
    "GitHubTokenSource",
    "ModelCatalogPage",
    "ResponsesHeadersPendingTransportError",
    "build_identity_headers",
    "build_request_headers",
    "fetch_models",
    "infer_account_type",
    "is_responses_headers_pending_transport_error",
    "resolve_base_url",
]
