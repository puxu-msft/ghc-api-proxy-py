"""Standalone GitHub Copilot API client library.

Callers supply `GhcClientConfig` and `GitHubTokenSource`.
The model catalog is returned as raw wire data for the caller to validate with its own types.

In scope: token exchange, account probing, model catalog fetch, model-agnostic request building, and — since `app.auth` moved under it — where a GitHub token comes from in the first place.
Out of scope: model name resolution, body translation, history, retry orchestration.

This said "Imports nothing from `app.*`" until 2026-08-21. It had already stopped being true: `errors.py` imports `app.pipeline.exceptions` to normalise SDK failures into the vocabulary the pipeline speaks, and `auth/` reaches `app.config` for the token file's location and for the one environment variable name. Nothing enforced the claim, so it went stale silently — which is the reason to state what the dependencies are instead of that there are none.
"""

from app.ghc_client.account import GitHubAccountClient, infer_account_type
from app.ghc_client.client import GhcApiClient
from app.ghc_client.config import GhcClientConfig, resolve_api_base_url
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
    "resolve_api_base_url",
]
