"""Composition root for the new request path.

Builds the chain a request travels: config -> provider -> pipeline -> driver.
Everything is constructed once at startup and handed down, so nothing reaches for a global.
"""

from dataclasses import dataclass, field
from pathlib import Path

import httpx
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.auth.providers import (
    CLITokenProvider,
    EnvTokenProvider,
    FileTokenProvider,
    GitHubTokenManager,
)
from app.config.paths import expand_user_path, tokenization_state_path
from app.config.schema import ProxyConfig
from app.ghc_client import (
    CopilotTokenManager,
    GhcApiClient,
    GhcClientConfig,
    build_identity_headers,
    build_request_headers,
)
from app.model_provider import (
    PROVIDER_TYPE,
    GithubCopilotProvider,
    ModelProvider,
    ProviderRegistry,
    resolve_default_name,
)
from app.observability.active_requests import ActiveRequestRegistry
from app.observability.terminal import TerminalCapabilities, detect_terminal
from app.pipeline.events import FrozenSubscribers, SubscriberRegistry
from app.pipeline.rate_limiting import RateLimiter
from app.pipeline.request import RequestContext
from app.pipeline.subscribers import register_builtin_subscribers
from app.pipeline.translation_driver.registry import TranslatorRegistry, default_registry
from app.tokenization.state_store import TokenizationStateStore
from app.upstream.copilot import GitHubTokenSourceAdapter


@dataclass(frozen=True, slots=True)
class TransportOptions:
    """What the transport settings mean for the outbound client.

    Kept separate from constructing the client so the decision can be asserted without reaching
    into a third-party object's private state.
    """

    proxy: str | None
    http2: bool
    keepalive_expiry: float | None


def transport_options(config: ProxyConfig) -> TransportOptions:
    """Read the transport settings.

    `proxy` applies to every outgoing request, not only the model ones, as the spec states.
    `tcp_keepalive_interval` uses 0 to disable.

    `http2` is read straight from its own key. It used to be derived from `http2_ping_interval > 0`, so a key named after a ping interval silently decided which protocol we spoke — and an operator looking for the HTTP/1.1 switch had no reason to look there. `http2_ping_interval` is now inert: neither httpx 0.28.1 nor httpcore 1.0.9 offers a PING interval to set, so it never produced a ping in the first place.
    """
    transport = config.upstream_transport
    keepalive = transport.tcp_keepalive_interval
    return TransportOptions(
        proxy=config.proxy or None,
        http2=transport.http2,
        keepalive_expiry=float(keepalive) if keepalive > 0 else None,
    )


def build_http_client(config: ProxyConfig) -> httpx.AsyncClient:
    options = transport_options(config)
    return httpx.AsyncClient(
        proxy=options.proxy,
        http2=options.http2,
        limits=httpx.Limits(keepalive_expiry=options.keepalive_expiry),
    )


@dataclass(slots=True)
class Chain:
    """Everything a request handler needs, built once."""

    config: ProxyConfig
    providers: ProviderRegistry
    translators: TranslatorRegistry
    subscribers: FrozenSubscribers[RequestContext]
    http_client: httpx.AsyncClient
    rate_limiters: dict[str, RateLimiter] = field(default_factory=lambda: dict[str, RateLimiter]())
    # Who is in flight right now. Always maintained, whether or not anything renders it: the cost is one dict entry per request, and making it conditional would mean the footer shows an empty line for its first few seconds after being switched on.
    active_requests: ActiveRequestRegistry = field(default_factory=ActiveRequestRegistry)
    # Probed once, here, and shared by the footer and the log lines. Asking twice invites two answers that disagree, and a log stream that emits a glyph the footer has already decided this terminal cannot encode is exactly the kind of split nobody thinks to look for.
    capabilities: TerminalCapabilities = field(default_factory=detect_terminal)
    # What the `local` token counter has learnt. Constructing it touches nothing; `load()` does.
    tokenization: TokenizationStateStore = field(
        default_factory=lambda: TokenizationStateStore(tokenization_state_path())
    )

    def rate_limiter_for(self, provider_name: str) -> RateLimiter:
        return self.rate_limiters[provider_name]

    async def aclose(self) -> None:
        await self.http_client.aclose()


def github_token_path(config: ProxyConfig, provider_name: str = "") -> Path | None:
    """Where a provider's GitHub token file lives, or None to use the default location.

    The spec spells it with `$XDG_DATA_HOME`, which is unset on a default install.
    """
    provider_config = config.model_providers.get(provider_name) if provider_name else None
    configured = provider_config.github_token_file if provider_config else ""
    return expand_user_path(configured) if configured else None


def build_github_token_source(
    config: ProxyConfig,
    provider_name: str = "",
) -> GitHubTokenSourceAdapter:
    """Assemble the CLI/env/file provider chain the host owns.

    The library only wants a token string, so the chain stays on this side of the boundary.
    A provider naming `github_token_file` points the file step at it, else the default location.
    """
    return GitHubTokenSourceAdapter(
        GitHubTokenManager(
            [
                CLITokenProvider(None),
                EnvTokenProvider(),
                FileTokenProvider(github_token_path(config, provider_name)),
            ]
        )
    )


def build_copilot_provider(
    name: str,
    config: ProxyConfig,
    *,
    http_client: httpx.AsyncClient,
    token_manager: CopilotTokenManager,
    interaction_id: str,
) -> GithubCopilotProvider:
    provider_config = config.model_providers[name]
    ghc_config = GhcClientConfig(
        api_base_url_override=provider_config.api_base_url,
        auth_base_url_override=provider_config.auth_base_url,
    )
    base_url = ghc_config.api_base_url
    client = GhcApiClient(
        AsyncOpenAI(
            api_key="proxy-managed",
            base_url=base_url,
            http_client=http_client,
            max_retries=0,
        ),
        AsyncAnthropic(
            api_key="proxy-managed",
            base_url=base_url,
            http_client=http_client,
            max_retries=0,
        ),
        token_manager,
        ghc_config,
        interaction_id=interaction_id,
    )
    return GithubCopilotProvider(
        name,
        client,
        provider_config,
        http_client=http_client,
        base_url=base_url,
    )


def build_chain(
    config: ProxyConfig,
    *,
    http_client: httpx.AsyncClient,
    providers: dict[str, ModelProvider] | None = None,
    subscribers: SubscriberRegistry[RequestContext] | None = None,
    interaction_id: str = "interaction",
) -> Chain:
    """Assemble the chain.

    `providers` is injectable so a test can drive the whole path without reaching the network.
    """
    if providers is None:
        built: dict[str, ModelProvider] = {}
        for name, provider_config in config.model_providers.items():
            if provider_config.type != PROVIDER_TYPE:
                raise ValueError(f"unsupported provider type {provider_config.type!r}")
            # Per provider: each may name its own token file.
            token_source = build_github_token_source(config, name)
            ghc_config = GhcClientConfig(
                api_base_url_override=provider_config.api_base_url,
                auth_base_url_override=provider_config.auth_base_url,
            )
            token_manager = CopilotTokenManager(
                token_source,
                http_client,
                auth_base_url=ghc_config.auth_base_url,
                identity_headers=build_identity_headers(ghc_config),
            )
            built[name] = build_copilot_provider(
                name,
                config,
                http_client=http_client,
                token_manager=token_manager,
                interaction_id=interaction_id,
            )
        providers = built

    # The built-ins go into whatever registry the caller brought, so their order is resolved together with anything a caller added rather than in a second, separate pass.
    subscriber_registry = subscribers if subscribers is not None else SubscriberRegistry[RequestContext]()
    # Every provider's list, merged. Which provider serves a request is decided per request, and a
    # model id is unique across the catalog, so there is nothing for a per-provider lookup to
    # disambiguate here that this does not already answer.
    web_search_models = frozenset(
        model
        for provider in config.model_providers.values()
        for model in provider.models_support_web_search
    )
    register_builtin_subscribers(subscriber_registry, web_search_models=web_search_models)

    return Chain(
        config=config,
        providers=ProviderRegistry(providers, default=resolve_default_name(config)),
        translators=default_registry(config.model_translation),
        subscribers=subscriber_registry.freeze(),
        http_client=http_client,
        # One limiter per provider: a limit on one upstream must not throttle another.
        rate_limiters={name: RateLimiter(config.reactive_rate_limiter) for name in providers},
    )


async def refresh_catalogs(chain: Chain) -> None:
    """Populate every provider's catalog.

    Routing fails closed on capability, so an empty catalog rejects every request until this runs.

    No headers parameter: each provider authenticates its own refresh from its own token manager.
    One taken from a caller would be captured once and expire, and having the parameter at all
    suggested authentication was the caller's job when nothing was in fact supplying it.
    """
    for name in chain.providers.names:
        await chain.providers.get(name).refresh_catalog()


__all__ = [
    "Chain",
    "TransportOptions",
    "build_chain",
    "build_copilot_provider",
    "build_github_token_source",
    "build_http_client",
    "build_request_headers",
    "github_token_path",
    "refresh_catalogs",
    "transport_options",
]
