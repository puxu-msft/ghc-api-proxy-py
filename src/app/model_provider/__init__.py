"""Abstraction over upstream model providers.

GitHub Copilot and Xingchen are instances: each owns a catalog and the endpoints it can drive.
Callers route through the shared protocol without depending on either concrete provider.
"""

from app.model_provider.base import CatalogProvider, ModelProvider
from app.model_provider.codebuddy import PROVIDER_TYPE as CODEBUDDY_PROVIDER_TYPE
from app.model_provider.codebuddy import CodebuddyProvider
from app.model_provider.github_copilot import (
    PROVIDER_TYPE as GITHUB_COPILOT_PROVIDER_TYPE,
)
from app.model_provider.github_copilot import GithubCopilotProvider
from app.model_provider.registry import (
    ProviderNotConfigured,
    ProviderRegistry,
    resolve_default_name,
)
from app.model_provider.types import (
    CapabilityMissing,
    CatalogSnapshot,
    CatalogSource,
    DescriptorProviderMismatch,
    EndpointNotImplemented,
    EndpointNotSupported,
    ModelDescriptor,
    ModelEndpoint,
    PromptTokenLimits,
    ProviderError,
    ResolvedEndpoints,
    UnknownModel,
    model_type_of,
    parse_endpoints,
    parse_prompt_token_limits,
    require_descriptor_owner,
    require_endpoint,
    resolve_endpoints,
)
from app.model_provider.xingchen import (
    PROVIDER_TYPE as XINGCHEN_PROVIDER_TYPE,
)
from app.model_provider.xingchen import XingchenClient, XingchenProvider

__all__ = [
    "CODEBUDDY_PROVIDER_TYPE",
    "GITHUB_COPILOT_PROVIDER_TYPE",
    "XINGCHEN_PROVIDER_TYPE",
    "CapabilityMissing",
    "CatalogProvider",
    "CatalogSnapshot",
    "CatalogSource",
    "CodebuddyProvider",
    "DescriptorProviderMismatch",
    "EndpointNotImplemented",
    "EndpointNotSupported",
    "GithubCopilotProvider",
    "ModelDescriptor",
    "ModelEndpoint",
    "ModelProvider",
    "PromptTokenLimits",
    "ProviderError",
    "ProviderNotConfigured",
    "ProviderRegistry",
    "ResolvedEndpoints",
    "UnknownModel",
    "XingchenClient",
    "XingchenProvider",
    "model_type_of",
    "parse_endpoints",
    "parse_prompt_token_limits",
    "require_descriptor_owner",
    "require_endpoint",
    "resolve_default_name",
    "resolve_endpoints",
]
