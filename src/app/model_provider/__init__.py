"""Abstraction over upstream model providers.

GitHub Copilot is one instance: a single provider offering model endpoints in several formats.
Other providers with other endpoints can be added without changing the callers.
"""

from app.model_provider.base import ModelProvider
from app.model_provider.github_copilot import PROVIDER_TYPE, GithubCopilotProvider
from app.model_provider.registry import (
    ProviderNotConfigured,
    ProviderRegistry,
    resolve_default_name,
)
from app.model_provider.types import (
    CapabilityMissing,
    EndpointNotImplemented,
    EndpointNotSupported,
    ModelDescriptor,
    ModelEndpoint,
    ProviderError,
    ResolvedEndpoints,
    UnknownModel,
    parse_endpoints,
    require_endpoint,
    resolve_endpoints,
)

__all__ = [
    "PROVIDER_TYPE",
    "CapabilityMissing",
    "EndpointNotImplemented",
    "EndpointNotSupported",
    "GithubCopilotProvider",
    "ModelDescriptor",
    "ModelEndpoint",
    "ModelProvider",
    "ProviderError",
    "ProviderNotConfigured",
    "ProviderRegistry",
    "ResolvedEndpoints",
    "UnknownModel",
    "parse_endpoints",
    "require_endpoint",
    "resolve_default_name",
    "resolve_endpoints",
]
