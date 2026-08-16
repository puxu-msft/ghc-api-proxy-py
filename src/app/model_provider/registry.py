"""Builds providers from configuration and answers which one to use."""

from collections.abc import Mapping

from app.config.schema import ProxyConfig
from app.model_provider.base import ModelProvider
from app.model_provider.types import ProviderError


class ProviderNotConfigured(ProviderError):
    def __init__(self, name: str) -> None:
        super().__init__(f"no model provider named {name!r} is configured")
        self.name = name


class ProviderRegistry:
    """The configured providers, with one designated default.

    `default_model_provider` must name a configured provider.
    An unset or dangling name fails here rather than at the first request.
    """

    def __init__(self, providers: Mapping[str, ModelProvider], *, default: str) -> None:
        if default not in providers:
            raise ProviderNotConfigured(default)
        self._providers = dict(providers)
        self._default = default

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._providers)

    @property
    def default(self) -> ModelProvider:
        return self._providers[self._default]

    @property
    def default_name(self) -> str:
        return self._default

    def get(self, name: str) -> ModelProvider:
        provider = self._providers.get(name)
        if provider is None:
            raise ProviderNotConfigured(name)
        return provider


def resolve_default_name(config: ProxyConfig) -> str:
    """Pick the default provider name.

    A single configured provider needs no explicit choice; more than one does.
    Guessing would silently route to an upstream the operator did not name.
    """
    if config.default_model_provider:
        return config.default_model_provider
    if len(config.model_providers) == 1:
        return next(iter(config.model_providers))
    raise ProviderNotConfigured("")
