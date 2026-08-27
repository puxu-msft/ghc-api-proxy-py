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
    """The configured providers, with one designated default and an optional fallback.

    `default_model_provider` must name a configured provider.
    An unset or dangling name fails here rather than at the first request.

    `fallback_model_provider` may be empty — that is a deployment choosing to refuse a request whose mapping named an unknown provider, rather than serve it from somewhere nobody asked for. But a **dangling** fallback fails here for the same reason a dangling default does: it is a name that will never resolve, and finding that out at start-up costs nothing while finding it out on the first typo'd request costs a rejected request and a puzzled reader.
    """

    def __init__(
        self,
        providers: Mapping[str, ModelProvider],
        *,
        default: str,
        fallback: str = "",
    ) -> None:
        if default not in providers:
            raise ProviderNotConfigured(default)
        if fallback and fallback not in providers:
            raise ProviderNotConfigured(fallback)
        self._providers = dict(providers)
        self._default = default
        self._fallback = fallback

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._providers)

    @property
    def default(self) -> ModelProvider:
        return self._providers[self._default]

    @property
    def default_name(self) -> str:
        return self._default

    @property
    def fallback_name(self) -> str:
        """The configured fallback, or `""` when the deployment set none.

        Returned as a name rather than a provider because the empty case is meaningful and a caller has to branch on it anyway; handing back `None` here would only move that branch.
        """
        return self._fallback

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
