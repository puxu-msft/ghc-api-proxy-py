"""Composition root for the new request path.

Builds the chain a request travels: config -> provider -> pipeline -> driver.
Everything is constructed once at startup and handed down, so nothing reaches for a global.
"""

import logging
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpcore
import httpx
from anthropic import AsyncAnthropic
from httpcore._async.http_proxy import AsyncForwardHTTPConnection, AsyncTunnelHTTPConnection
from httpcore._async.interfaces import AsyncConnectionInterface
from httpx._utils import get_environment_proxies
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
from app.pipeline.subscribers.hosted_web_search import compile_supported
from app.pipeline.translation_driver.registry import TranslatorRegistry, default_registry
from app.tokenization.state_store import TokenizationStateStore
from app.upstream.copilot import GitHubTokenSourceAdapter
from app.upstream.stream_cap import cap_streams_per_connection

logger = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True)
class TransportOptions:
    """What the transport settings mean for the outbound client.

    Kept separate from constructing the client so the decision can be asserted without reaching
    into a third-party object's private state.
    """

    proxy: str | None
    http2: bool
    socket_options: tuple[tuple[int, int, int], ...] | None
    # 0 = unlimited, which is httpx's own behaviour.
    max_streams_per_connection: int


# With idle and interval both set to the configured value, a peer that has gone away is noticed after roughly `interval * (1 + probes)`. Not a key of its own: what an operator wants to choose is how long to wait, and one number already says that.
_KEEPALIVE_PROBES = 4


def _keepalive_socket_options(interval: int) -> tuple[tuple[int, int, int], ...] | None:
    """Turn a keep-alive interval into socket options, or `None` when it is switched off.

    `SO_KEEPALIVE` is portable; the three that say *how long* are not. `TCP_KEEPIDLE` is the Linux spelling and `TCP_KEEPALIVE` the macOS one for the same thing, and on Windows any of the three may be absent. What is missing is named in a warning rather than dropped quietly, because the failure it produces — keep-alive on, but with the system's idle time instead of the configured one, which on Linux defaults to two hours — looks from the outside exactly like the setting having no effect at all. That is the shape of defect this whole change exists to remove.
    """
    if interval <= 0:
        return None
    options: list[tuple[int, int, int]] = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]
    missing: list[str] = []
    for names, value in (
        (("TCP_KEEPIDLE", "TCP_KEEPALIVE"), interval),
        (("TCP_KEEPINTVL",), interval),
        (("TCP_KEEPCNT",), _KEEPALIVE_PROBES),
    ):
        for name in names:
            option = getattr(socket, name, None)
            if option is not None:
                options.append((socket.IPPROTO_TCP, option, value))
                break
        else:
            missing.append(" / ".join(names))
    if missing:
        logger.warning(
            "TCP keep-alive is on but %s is unavailable on this platform, so the system's own timing applies for it rather than the configured value",
            ", ".join(missing),
        )
    return tuple(options)


def transport_options(config: ProxyConfig) -> TransportOptions:
    """Read the transport settings.

    `proxy` applies to every outgoing request, not only the model ones, as the spec states.

    `tcp_keepalive_interval` is a real TCP keep-alive: it was mapped to the connection pool's idle expiry until 2026-08-20, which never writes to the socket and does not apply while a request is in flight. Nothing here configures pooling any more — the 15 seconds that mapping produced was a side effect of the defect, not a setting anyone chose, and httpx's own defaults apply now.

    `http2` is read straight from its own key. It used to be derived from `http2_ping_interval > 0`, so a key named after a ping interval silently decided which protocol we spoke — and an operator looking for the HTTP/1.1 switch had no reason to look there. `http2_ping_interval` is now inert: neither httpx 0.28.1 nor httpcore 1.0.9 offers a PING interval to set, so it never produced a ping in the first place.
    """
    transport = config.upstream_transport
    return TransportOptions(
        proxy=config.proxy or None,
        http2=transport.http2,
        socket_options=_keepalive_socket_options(transport.tcp_keepalive_interval),
        max_streams_per_connection=transport.max_streams_per_connection,
    )


def build_http_client(config: ProxyConfig) -> httpx.AsyncClient:
    """Build the outbound client, with the keep-alive the settings ask for.

    Socket options can only be given to a transport, and handing `AsyncClient` a transport is also how you switch off its own reading of `HTTP_PROXY` / `HTTPS_PROXY` — `allow_env_proxies` in `httpx/_client.py` is `trust_env and transport is None`. So the environment map is rebuilt here and mounted, because losing proxy support is exactly the kind of change that would not show up until someone behind a proxy could not reach upstream at all.

    One path the keep-alive does not reach, and says so out loud: httpx builds a SOCKS proxy through `httpcore.AsyncSOCKSProxy`, which takes no `socket_options` at all — the gap is in httpcore, not in the wiring here. Measured on a real SOCKS5 connection: `SO_KEEPALIVE` reads back 0. Ruled 2026-08-20 to accept that and warn rather than take over the pool behind a network backend of our own.

    Worth being exact about what any of this buys with a proxy in the way. TCP keep-alive is per-connection and a proxy terminates the connection: measured, our socket's peer is the origin when direct and the proxy when tunnelling. So proxied, this probes the hop to the proxy — the proxy's own connection to upstream is a socket we neither see nor set options on. Only the direct case says anything about upstream itself, which is what this deployment uses.
    """
    options = transport_options(config)

    def transport(proxy: str | None) -> httpx.AsyncHTTPTransport:
        # No `limits`. Pooling is httpx's to decide and always was; the previous code passed a `Limits` carrying only an expiry, which left the two connection caps at `None` and httpcore reads `None` as `sys.maxsize`. Naming one field of it had removed the caps httpx would otherwise have applied.
        built = httpx.AsyncHTTPTransport(
            proxy=proxy,
            http2=options.http2,
            socket_options=options.socket_options,
        )
        if options.socket_options is not None:
            _keep_proxy_connections_alive(built, options.socket_options)
        return built

    direct = transport(None)
    _warn_about_socks(options)
    client = httpx.AsyncClient(
        transport=transport(options.proxy) if options.proxy is not None else direct,
        mounts=_proxy_mounts(options.proxy, transport, direct),
        http2=options.http2,
    )
    if options.max_streams_per_connection > 0:
        # After the client is built, not instead of building it: the cap wraps the pool httpx configured rather than replacing it, so every setting httpx passed through — and every one it gains later — is kept. See `app.upstream.stream_cap`.
        #
        # And after `_keep_proxy_connections_alive`, not before. Both patch `create_connection` on the same proxy pool, so whichever runs second wraps the first. This way round the cap wraps the keep-alive closure and both apply; the other way round the keep-alive closure is assigned straight over the cap's, which then becomes unreachable — with no error raised and the socket options still perfectly correct. Measured on a real CONNECT tunnel: five concurrent requests share one h2 tunnel instead of the four connections a cap of 2 produces. `test_a_proxy_pool_keeps_both_the_cap_and_the_keepalive` is what makes swapping these two lines go red.
        cap_streams_per_connection(client, options.max_streams_per_connection)
    return client


def _keep_proxy_connections_alive(
    transport: httpx.AsyncHTTPTransport,
    socket_options: tuple[tuple[int, int, int], ...],
) -> None:
    """Put the socket options back on the connections a proxy pool builds.

    `httpcore.AsyncHTTPProxy` takes `socket_options`, stores it, hands it to `super().__init__` — and then builds its connections in `create_connection` without it. Every parameter along the way reads as correctly threaded; the socket disagrees. Measured through a real forward proxy before this existed: `SO_KEEPALIVE` 0, identical to the control with the keep-alive switched off.

    Patches the one method that is wrong on the pool httpx already configured, rather than substituting a pool of our own. `app.upstream.stream_cap` reached the same conclusion for the same reason: a replacement pool has to reproduce every setting `AsyncHTTPTransport` passed through — `retries`, `local_address`, `uds` among them — and anything forgotten is lost silently and stays lost as httpx gains more. An earlier version of this did substitute the pool, and did forget three of them.

    `AsyncSOCKSProxy` is not helped: it has no `socket_options` parameter to forward. `_warn_about_socks` says so.
    """
    pool = getattr(transport, "_pool", None)
    if not isinstance(pool, httpcore.AsyncHTTPProxy):
        return

    def create_connection(origin: httpcore.Origin) -> AsyncConnectionInterface:
        if origin.scheme == b"http":
            return AsyncForwardHTTPConnection(
                proxy_origin=pool._proxy_url.origin,  # pyright: ignore[reportPrivateUsage]
                proxy_headers=pool._proxy_headers,  # pyright: ignore[reportPrivateUsage]
                remote_origin=origin,
                keepalive_expiry=pool._keepalive_expiry,  # pyright: ignore[reportPrivateUsage]
                network_backend=pool._network_backend,  # pyright: ignore[reportPrivateUsage]
                proxy_ssl_context=pool._proxy_ssl_context,  # pyright: ignore[reportPrivateUsage]
                socket_options=socket_options,
            )
        return AsyncTunnelHTTPConnection(
            proxy_origin=pool._proxy_url.origin,  # pyright: ignore[reportPrivateUsage]
            proxy_headers=pool._proxy_headers,  # pyright: ignore[reportPrivateUsage]
            remote_origin=origin,
            ssl_context=pool._ssl_context,  # pyright: ignore[reportPrivateUsage]
            proxy_ssl_context=pool._proxy_ssl_context,  # pyright: ignore[reportPrivateUsage]
            keepalive_expiry=pool._keepalive_expiry,  # pyright: ignore[reportPrivateUsage]
            http1=pool._http1,  # pyright: ignore[reportPrivateUsage]
            http2=pool._http2,  # pyright: ignore[reportPrivateUsage]
            network_backend=pool._network_backend,  # pyright: ignore[reportPrivateUsage]
            socket_options=socket_options,
        )

    pool.create_connection = create_connection


def _warn_about_socks(options: TransportOptions) -> None:
    """Say so when a SOCKS proxy is in play, because the keep-alive cannot reach it.

    `httpcore.AsyncSOCKSProxy` takes no `socket_options` at all — unlike the HTTP proxy, where the parameter exists and is merely dropped, so `_keep_proxy_connections_alive` can put it back. Measured on a real SOCKS5 connection: `SO_KEEPALIVE` reads back 0.

    Looks at the environment as well as the config. Warning only about a configured proxy would have left `ALL_PROXY=socks5://…` failing in exactly the same way and saying nothing, which is the shape of defect this change exists to remove.

    Only the origin is logged. A proxy URL may carry credentials, and this line is not worth putting them in an operator's log to produce.
    """
    if options.socket_options is None:
        return
    if options.proxy is not None:
        candidates = [options.proxy]
    else:
        candidates = [url for url in get_environment_proxies().values() if url is not None]
    for origin in sorted({_origin_of(url) for url in candidates if _is_socks(url)}):
        logger.warning(
            "proxy %s is SOCKS, and httpcore sets no socket options on that path: tcp_keepalive_interval does not apply to connections made through it",
            origin,
        )


def _origin_of(url: str) -> str:
    """Scheme, host and port — the part of a proxy URL that names it, without the credentials it may carry.

    Brackets go back on an IPv6 host, because httpx hands one back without them and `socks5://fe80::1:1080` cannot be read back as a host and a port — nor as anything else. The warning says it is printing an origin, so it should print one.

    `is not None` rather than truthiness: httpx parses an explicit `:0` as the integer 0, and testing the port for truth would print it as though no port had been given.
    """
    parsed = httpx.URL(url)
    host = f"[{parsed.host}]" if ":" in parsed.host else parsed.host
    return f"{parsed.scheme}://{host}:{parsed.port}" if parsed.port is not None else f"{parsed.scheme}://{host}"


def _is_socks(proxy: str | None) -> bool:
    return proxy is not None and proxy.lower().startswith("socks")


def _proxy_mounts(
    configured: str | None,
    transport: Callable[[str | None], httpx.AsyncHTTPTransport],
    direct: httpx.AsyncHTTPTransport,
) -> dict[str, httpx.AsyncBaseTransport]:
    """The per-scheme proxies httpx would have read from the environment, as transports of ours.

    Empty when `proxy` is configured, which is what httpx does too: an explicit proxy is `all://` and the environment is not consulted. A `None` in the environment map is a `NO_PROXY` entry, and it maps to the one shared direct transport rather than being dropped — dropping it would send that host through whichever broader pattern matched next, and giving each rule a transport of its own would give each its own pool, multiplying the connection cap by the number of `NO_PROXY` rules.

    Reaches into `httpx._utils` for the environment map rather than reimplementing `NO_PROXY` matching. A httpx that moves it fails at import, so this cannot decay into quietly returning no mounts.
    """
    if configured is not None:
        return {}
    return {
        pattern: direct if url is None else transport(url)
        for pattern, url in get_environment_proxies().items()
    }


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
    # Every provider's patterns, merged. Which provider serves a request is decided per request, and a model id is unique across the catalog, so there is nothing for a per-provider lookup to disambiguate here that this does not already answer.
    #
    # Compiled here rather than per request, which also puts a pattern that does not compile at startup — in the config's own words — instead of inside whichever request first reached the gate.
    web_search_models = compile_supported(
        pattern
        for provider in config.model_providers.values()
        for pattern in provider.models_support_web_search
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
