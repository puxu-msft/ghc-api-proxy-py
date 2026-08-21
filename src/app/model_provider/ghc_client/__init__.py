"""The GitHub Copilot API client, backing the provider of the same name.

Callers supply `GhcClientConfig` and `GitHubTokenSource`.
The model catalog is returned as raw wire data for the caller to validate with its own types.

In scope: token exchange, account probing, model catalog fetch, model-agnostic request building, and — since `app.auth` moved under it — where a GitHub token comes from in the first place.
Out of scope: model name resolution, body translation, history, retry orchestration.

It sat at `app.ghc_client` until 2026-08-21, as though talking to Copilot were a peer of the provider abstraction rather than one instance of it. It is one, and it is currently the only one; a second provider gets its own sibling here rather than another top-level package.

The docstring also said "Imports nothing from `app.*`", which had already stopped being true: `errors.py` imports `app.pipeline.exceptions` to normalise SDK failures into the vocabulary the pipeline speaks, and `auth/` reaches `app.config` for the token file's location and for the one environment variable name. Nothing enforced the claim, so it went stale in silence — which is the reason to state what the dependencies are instead of that there are none.
"""

from app.model_provider.ghc_client.account import GitHubAccountClient, infer_account_type
from app.model_provider.ghc_client.client import GhcApiClient
from app.model_provider.ghc_client.config import GhcClientConfig, resolve_api_base_url
from app.model_provider.ghc_client.device_flow import (
    DeviceCode,
    DeviceFlowClient,
    DeviceFlowError,
)
from app.model_provider.ghc_client.headers import build_identity_headers, build_request_headers
from app.model_provider.ghc_client.models import ModelCatalogPage, fetch_models
from app.model_provider.ghc_client.tokens import (
    CopilotTokenInfo,
    CopilotTokenManager,
    GitHubTokenSource,
)
from app.model_provider.ghc_client.transport import (
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
