"""Composition root for the new request path.

Builds the chain a request travels: config -> provider -> pipeline -> driver.
Everything is constructed once at startup and handed down, so nothing reaches for a global.
"""

import logging
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib.request import getproxies

import httpcore2
import httpx2
from anthropic import AsyncAnthropic
from httpcore2._async.http_proxy import AsyncForwardHTTPConnection, AsyncTunnelHTTPConnection
from httpcore2._async.interfaces import AsyncConnectionInterface
from httpx2._utils import get_environment_proxies
from openai import AsyncOpenAI

from app.config.paths import expand_user_path
from app.config.schema import ProxyConfig
from app.core.chain import Chain
from app.model_provider import (
    PROVIDER_TYPE,
    GithubCopilotProvider,
    ModelProvider,
    ProviderNotConfigured,
    ProviderRegistry,
    resolve_default_name,
)
from app.model_provider.ghc_client import (
    CopilotTokenManager,
    GhcApiClient,
    GhcClientConfig,
    GitHubAccountClient,
    build_identity_headers,
    build_request_headers,
    infer_account_type,
    resolve_api_base_url,
)
from app.model_provider.ghc_client.auth.providers import (
    CLITokenProvider,
    EnvTokenProvider,
    FileTokenProvider,
    GitHubTokenManager,
    NoGitHubToken,
)
from app.model_provider.ghc_client.config import AccountType
from app.pipeline.events import SubscriberRegistry
from app.pipeline.model_resolution import inspect_mappings
from app.pipeline.rate_limiting import RateLimiter
from app.pipeline.request import RequestContext
from app.pipeline.request_headers import compile_beta_flag_denials
from app.pipeline.subscribers import register_builtin_subscribers
from app.pipeline.subscribers.anthropic_cache_control import compile_sanitize_table
from app.pipeline.subscribers.hosted_web_search import compile_supported_by_provider
from app.pipeline.translation_driver.registry import default_registry
from app.upstream.copilot import GitHubTokenSourceAdapter
from app.upstream.stream_cap import cap_streams_per_connection

logger = logging.getLogger(__name__)

# The two answers that mean the credentials are wrong rather than that GitHub was briefly unreachable. Ruled 2026-08-22: these stop the process, because a token GitHub refuses will be refused by every request that follows and failing at startup says so once instead of once per request. Everything else — a timeout, a reset, a 5xx, a 429 — is a moment in GitHub's day, and a proxy that will not start because of one is worse than a proxy that starts on the default host: under socket activation the old process has already handed over its listener, so refusing to start is an outage rather than a hold.
#
# Degrading is not silent. It is logged, and an enterprise account left on the individual host fails loudly on its first request rather than answering wrongly.
_CREDENTIALS_REFUSED = frozenset({401, 403})

@dataclass(frozen=True, slots=True)
class TransportOptions:
    """What the transport settings mean for the outbound client.

    Kept separate from constructing the client so the decision can be asserted without reaching into a third-party object's private state.

    The proxy arrives as three fields rather than one because `config.example.yaml` states three tiers — CLI `--proxy`, then `HTTP_PROXY` / `HTTPS_PROXY`, then this setting — and a single string cannot say which tier it came from. Everything below the environment (YAML, `GHC_API_PROXY_PROXY`, bundled) is one tier, so one bit of provenance is all three tiers need.
    """

    # True when `--proxy` was given at all — an empty value included. Tier 1 having been exercised is what shuts tiers 2 and 3 out, not the value being non-empty: `--proxy ""` is an operator overriding a configured proxy back to direct, ruled 2026-08-21, and reading it as "no tier 1 after all" would hand the decision back to the environment they were overriding.
    proxy_from_cli: bool
    # Tier 1's value. `None` with `proxy_from_cli` set means `--proxy ""`.
    cli_proxy: str | None
    # Tier 3. Mounted *under* the environment as `all://`, httpx's least specific pattern, so the environment's own entries win wherever they apply and this catches the schemes it does not name.
    setting_proxy: str | None
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


def transport_options(config: ProxyConfig, *, proxy_from_cli: bool) -> TransportOptions:
    """Read the transport settings.

    `proxy` applies to every outgoing request, not only the model ones, as the spec states.

    `proxy_from_cli` is required rather than defaulted, because the two answers produce different routing and a caller that forgot it would silently get the environment overriding a proxy the operator passed on the command line. A `TypeError` is the cheaper failure. It says whether the value in `config.proxy` arrived through `--proxy`: `load_proxy_config` merges CLI, `GHC_API_PROXY_PROXY` and YAML into that one field, so by the time it is a string its tier is no longer recoverable from it.

    `tcp_keepalive_interval` is a real TCP keep-alive: it was mapped to the connection pool's idle expiry until 2026-08-20, which never writes to the socket and does not apply while a request is in flight. Nothing here configures pooling any more — the 15 seconds that mapping produced was a side effect of the defect, not a setting anyone chose, and httpx's own defaults apply now.

    `http2` is read straight from its own key. It used to be derived from `http2_ping_interval > 0`, so a key named after a ping interval silently decided which protocol we spoke — and an operator looking for the HTTP/1.1 switch had no reason to look there. `http2_ping_interval` is now inert: neither httpx nor httpcore offers a PING interval to set, so it never produced a ping in the first place.
    """
    transport = config.upstream_transport
    proxy = config.proxy or None
    return TransportOptions(
        proxy_from_cli=proxy_from_cli,
        cli_proxy=proxy if proxy_from_cli else None,
        setting_proxy=None if proxy_from_cli else proxy,
        http2=transport.http2,
        socket_options=_keepalive_socket_options(transport.tcp_keepalive_interval),
        max_streams_per_connection=transport.max_streams_per_connection,
    )


def build_http_client(
    config: ProxyConfig, *, proxy_from_cli: bool, warn_about_proxies: bool = True
) -> httpx2.AsyncClient:
    """Build the outbound client, with the keep-alive the settings ask for.

    Socket options can only be given to a transport, and handing `AsyncClient` a transport is also how you switch off its own reading of `HTTP_PROXY` / `HTTPS_PROXY` — `allow_env_proxies` in `httpx/_client.py` is `trust_env and transport is None`. So the environment map is rebuilt here and mounted, because losing proxy support is exactly the kind of change that would not show up until someone behind a proxy could not reach upstream at all.

    That rebuild is also what makes the priority `config.example.yaml` states implementable at all. `--proxy` is explicit and shuts the environment out; the `proxy` setting instead becomes an `all://` mount underneath the environment's, so the environment wins for the schemes it names and the setting catches the rest. Ruled 2026-08-21: per-scheme, not whole-tier. See `proxy_from_cli` on `transport_options` for why one bit is enough.

    One path the keep-alive does not reach, and says so out loud: httpx builds a SOCKS proxy through `httpcore.AsyncSOCKSProxy`, which takes no `socket_options` at all — the gap is in httpcore, not in the wiring here. Measured on a real SOCKS5 connection: `SO_KEEPALIVE` reads back 0. Ruled 2026-08-20 to accept that and warn rather than take over the pool behind a network backend of our own.

    Worth being exact about what any of this buys with a proxy in the way. TCP keep-alive is per-connection and a proxy terminates the connection: measured, our socket's peer is the origin when direct and the proxy when tunnelling. So proxied, this probes the hop to the proxy — the proxy's own connection to upstream is a socket we neither see nor set options on. Only the direct case says anything about upstream itself, which is what this deployment uses.
    """
    options = transport_options(config, proxy_from_cli=proxy_from_cli)

    def transport(proxy: str | None) -> httpx2.AsyncHTTPTransport:
        # No `limits`. Pooling is httpx's to decide and always was; the previous code passed a `Limits` carrying only an expiry, which left the two connection caps at `None` and httpcore reads `None` as `sys.maxsize`. Naming one field of it had removed the caps httpx would otherwise have applied.
        built = httpx2.AsyncHTTPTransport(
            proxy=proxy,
            http2=options.http2,
            socket_options=options.socket_options,
        )
        if options.socket_options is not None:
            _keep_proxy_connections_alive(built, options.socket_options)
        return built

    direct = transport(None)
    # One resolved map decides both the routing and the warning. Deriving them separately is what made the warning describe proxies the routing had already shadowed.
    resolved = _effective_proxies(options)
    # Once per process, not once per client. `_warn_about_socks` reasons about the environment's proxy map, which is the same for every client this process builds; its own docstring accepts over-reporting on the basis of one call per process, and that premise stopped holding when providers started getting a client each. The caller that builds the bootstrap client keeps the warning; the per-provider loop switches it off.
    if warn_about_proxies:
        _warn_about_socks(options, resolved)
    client = httpx2.AsyncClient(
        # Everything rides on mounts, including tier 1. `all://` matches every request, so this routes identically to handing the proxy to `transport=` — and it keeps one code path instead of a special case whose two halves drifted.
        transport=direct,
        mounts={
            pattern: direct if url is None else transport(url)
            for pattern, url in resolved.items()
        },
        http2=options.http2,
    )
    if options.max_streams_per_connection > 0:
        # After the client is built, not instead of building it: the cap wraps the pool httpx configured rather than replacing it, so every setting httpx passed through — and every one it gains later — is kept. See `app.upstream.stream_cap`.
        #
        # And after `_keep_proxy_connections_alive`, not before. Both patch `create_connection` on the same proxy pool, so whichever runs second wraps the first. This way round the cap wraps the keep-alive closure and both apply; the other way round the keep-alive closure is assigned straight over the cap's, which then becomes unreachable — with no error raised and the socket options still perfectly correct. Measured on a real CONNECT tunnel: five concurrent requests share one h2 tunnel instead of the four connections a cap of 2 produces. `test_a_proxy_pool_keeps_both_the_cap_and_the_keepalive` is what makes swapping these two lines go red.
        cap_streams_per_connection(client, options.max_streams_per_connection)
    return client


def _keep_proxy_connections_alive(
    transport: httpx2.AsyncHTTPTransport,
    socket_options: tuple[tuple[int, int, int], ...],
) -> None:
    """Put the socket options back on the connections a proxy pool builds.

    `httpcore.AsyncHTTPProxy` takes `socket_options`, stores it, hands it to `super().__init__` — and then builds its connections in `create_connection` without it. Every parameter along the way reads as correctly threaded; the socket disagrees. Measured through a real forward proxy before this existed: `SO_KEEPALIVE` 0, identical to the control with the keep-alive switched off.

    Patches the one method that is wrong on the pool httpx already configured, rather than substituting a pool of our own. `app.upstream.stream_cap` reached the same conclusion for the same reason: a replacement pool has to reproduce every setting `AsyncHTTPTransport` passed through — `retries`, `local_address`, `uds` among them — and anything forgotten is lost silently and stays lost as httpx gains more. An earlier version of this did substitute the pool, and did forget three of them.

    `AsyncSOCKSProxy` is not helped: it has no `socket_options` parameter to forward. `_warn_about_socks` says so.
    """
    pool = getattr(transport, "_pool", None)
    if not isinstance(pool, httpcore2.AsyncHTTPProxy):
        return

    def create_connection(origin: httpcore2.Origin) -> AsyncConnectionInterface:
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


def _warn_about_socks(options: TransportOptions, resolved: dict[str, str | None]) -> None:
    """Say so when a SOCKS proxy is in play, because the keep-alive cannot reach it.

    `httpcore.AsyncSOCKSProxy` takes no `socket_options` at all — unlike the HTTP proxy, where the parameter exists and is merely dropped, so `_keep_proxy_connections_alive` can put it back. Measured on a real SOCKS5 connection: `SO_KEEPALIVE` reads back 0.

    Reads the resolved map rather than the settings it came from, so a proxy the routing has already shadowed is not warned about. Warning only about a configured proxy would equally have left `ALL_PROXY=socks5://…` failing in exactly the same way and saying nothing, which is the shape of defect this change exists to remove.

    One over-report survives and is accepted: an `all://` SOCKS entry is still named when `http://` and `https://` are both set, so nothing would actually route through it. Removing that needs reachability analysis over the mount patterns, and the cheap direction to be wrong in is naming a proxy that carries nothing rather than staying silent about one that carries traffic.

    Only the origin is logged. A proxy URL may carry credentials, and this line is not worth putting them in an operator's log to produce.
    """
    if options.socket_options is None:
        return
    for origin in sorted(
        {_origin_of(url) for url in resolved.values() if url is not None and _is_socks(url)}
    ):
        # Why it does not apply belongs here rather than in the line: httpcore sets no socket options on the SOCKS path, which is an implementation fact the operator can do nothing with. What reaches them is which proxy and which setting, because that is what they can act on.
        logger.warning(
            "proxy %s is SOCKS: tcp_keepalive_interval does not apply to connections made through it",
            origin,
        )


def _origin_of(url: str) -> str:
    """Scheme, host and port — the part of a proxy URL that names it, without the credentials it may carry.

    Brackets go back on an IPv6 host, because httpx hands one back without them and `socks5://fe80::1:1080` cannot be read back as a host and a port — nor as anything else. The warning says it is printing an origin, so it should print one.

    `is not None` rather than truthiness: httpx parses an explicit `:0` as the integer 0, and testing the port for truth would print it as though no port had been given.
    """
    parsed = httpx2.URL(url)
    host = f"[{parsed.host}]" if ":" in parsed.host else parsed.host
    return f"{parsed.scheme}://{host}:{parsed.port}" if parsed.port is not None else f"{parsed.scheme}://{host}"


def _is_socks(proxy: str | None) -> bool:
    return proxy is not None and proxy.lower().startswith("socks")


def _environment_bypasses_everything() -> bool:
    """Whether `NO_PROXY` contains `*`, which means "ignore every proxy and go direct".

    Asked separately because `get_environment_proxies()` expresses that by returning an empty map — the same value it returns when the environment names no proxy at all. The two mean opposite things for the tier below: an environment that said nothing leaves the `proxy` setting in charge, and an environment that said `*` has just overruled it. Reading the emptiness of the map as "the environment is silent" routed every request through the setting when the operator had asked for none, and no existing test saw it because `*` is the one `NO_PROXY` form that produces no `all://<host>` entry to be outranked by.

    Reads the same source httpx does, so the two cannot disagree about what counts as `*`.
    """
    return any(host.strip() == "*" for host in getproxies().get("no", "").split(","))


def _effective_proxies(options: TransportOptions) -> dict[str, str | None]:
    """Which proxy each URL pattern resolves to, before any of it becomes a transport.

    The single source for both the mounts and the SOCKS warning. Deriving them separately is what let the warning name a proxy the routing had already shadowed.

    Tier 1 answers alone when it was given, `--proxy ""` included: an empty value is an operator overriding a configured proxy back to direct, and it must not fall through to the environment they were overriding.

    Otherwise the environment's own map applies, with the `proxy` setting under it as `all://` — httpx's least specific pattern, so a named scheme is resolved ahead of it and the `all://<host>` entries `NO_PROXY` produces ahead of that again. `ALL_PROXY` lands on the same `all://` key and therefore replaces the setting outright. `NO_PROXY=*` is the exception that cannot be expressed as a mount at all, so it is asked about directly.

    A `None` value is a `NO_PROXY` entry and becomes the one shared direct transport rather than being dropped — dropping it would send that host through whichever broader pattern matched next, and giving each rule a transport of its own would give each its own pool, multiplying the connection cap by the number of `NO_PROXY` rules.

    Reaches into `httpx._utils` for the environment map rather than reimplementing `NO_PROXY` matching. A httpx that moves it fails at import, so this cannot decay into quietly returning no mounts.
    """
    if options.proxy_from_cli:
        return {} if options.cli_proxy is None else {"all://": options.cli_proxy}
    environment = get_environment_proxies()
    if options.setting_proxy is None or _environment_bypasses_everything():
        return environment
    return {"all://": options.setting_proxy, **environment}


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


async def resolve_provider_base_urls(
    config: ProxyConfig,
    *,
    http_client: httpx2.AsyncClient,
) -> ProxyConfig:
    """Fill in the API base URL of every provider that did not name one, by asking GitHub what the subscription is.

    Two ways to reach a base URL and no third, ruled 2026-08-22: an operator writes the whole URL into `model_providers.<name>.api_base_url`, or this probes `/copilot_internal/user` and derives it from the plan. There is deliberately no `account_type` key — a name for the plan, kept in sync by hand with a subscription GitHub already knows about, is a third source of truth for the same fact.

    Here rather than inside `build_chain` because building a chain is otherwise pure — config in, wiring out — and all dozen of its callers, tests included, would have had to become async to carry a probe that only the two entry points serving real traffic need. What gets handed down is the resolved config, so nothing below this line learns that a probe happened.

    A missing GitHub token is not a failure. This chain starts without credentials and asks for them at the first request, so refusing to start because nobody has logged in yet would be this function inventing a startup gate that did not exist. Everything else the probe raises propagates: a token that exists and an answer we could not read is a real fault, and quietly falling back to the individual host would send an enterprise account's traffic to the wrong place — silently, which is the failure this change exists to remove.
    """
    resolved = dict(config.model_providers)
    changed = False
    for name, provider_config in config.model_providers.items():
        if provider_config.type != PROVIDER_TYPE or provider_config.api_base_url:
            continue
        auth_base_url = GhcClientConfig(
            auth_base_url_override=provider_config.auth_base_url
        ).auth_base_url
        try:
            token = await build_github_token_source(config, name).get_token()
        except NoGitHubToken:
            logger.info(
                "provider %s: no GitHub token yet, so the subscription was not probed", name
            )
            continue
        try:
            usage = await GitHubAccountClient(
                http_client, auth_base_url=auth_base_url
            ).get_copilot_usage(token)
        except httpx2.HTTPStatusError as error:
            if error.response.status_code in _CREDENTIALS_REFUSED:
                raise
            logger.warning(
                "provider %s: the subscription probe answered %s, so its API base URL stays at the default",
                name,
                error.response.status_code,
            )
            continue
        except httpx2.TransportError as error:
            logger.warning(
                "provider %s: the subscription probe could not reach %s (%s), so its API base URL stays at the default",
                name,
                auth_base_url,
                error,
            )
            continue
        inferred = infer_account_type(usage)
        if inferred is None:
            # Ambiguous rather than absent: the account answered, and nothing it said named a plan this maps. Said out loud because the default that follows is a guess, and a guess nobody was told about is how the wrong host stays wrong.
            logger.warning(
                "provider %s: the subscription named no plan this recognises, so its API base URL stays at the default",
                name,
            )
            continue
        base_url = resolve_api_base_url(GhcClientConfig(account_type=cast(AccountType, inferred)))
        logger.info("provider %s: subscription reads %s, so its API base URL is %s", name, inferred, base_url)
        # Revalidated rather than `model_copy(update=...)`. That call does not check the name it is given, which is exactly how `--ghc-api-base-url` spent three days writing a field that no longer existed and reporting nothing — the defect this function replaces. A misspelling here fails at startup instead.
        resolved[name] = type(provider_config).model_validate(
            {**provider_config.model_dump(), "api_base_url": base_url}
        )
        changed = True
    if not changed:
        return config
    # Revalidated for the same reason the per-provider write above is, and it is the same call that would otherwise sit twenty lines under a comment explaining why not to make it: `model_copy` does not check the name it is handed, so `model_provider` would return a config whose providers were never replaced, silently and with the right type.
    return ProxyConfig.model_validate(
        {
            **config.model_dump(),
            "model_providers": {name: p.model_dump() for name, p in resolved.items()},
        }
    )


def build_copilot_provider(
    name: str,
    config: ProxyConfig,
    *,
    http_client: httpx2.AsyncClient,
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
    http_client: httpx2.AsyncClient,
    providers: dict[str, ModelProvider] | None = None,
    subscribers: SubscriberRegistry[RequestContext] | None = None,
    interaction_id: str = "interaction",
    proxy_from_cli: bool = False,
) -> Chain:
    """Assemble the chain.

    `providers` is injectable so a test can drive the whole path without reaching the network. When it is supplied, no per-provider clients are built either — the caller owns whatever those providers talk through.

    `http_client` is still taken because the caller built one to resolve base URLs before this ran, and closing it stays the caller's business. It is no longer what the providers use.
    """
    # Everything that can be rejected without constructing anything, before anything is constructed. Two of these used to sit *after* the provider loop — `resolve_default_name` inside the `Chain(...)` call, and the registry's own name validation — so a one-letter typo in `fallback_model_provider` built one client per provider and then threw, leaving them with no reference and no way to close them. `build_chain` is synchronous and `AsyncClient.aclose()` is not, so there is no cleanup to write here; moving the checks in front of the allocation is the fix that a sync function can actually make.
    #
    # What that leaves: a failure *inside* the loop (an unreadable token path, say) still abandons the clients built so far. Those clients have never issued a request — nothing in this function does — so their connection pools are empty and no socket is open; what leaks is a Python object that the collector takes. That is why this is worth reordering rather than restructuring.
    default_name = resolve_default_name(config)
    for chosen in (default_name, config.fallback_model_provider):
        if chosen and chosen not in config.model_providers:
            raise ProviderNotConfigured(chosen)
    for name, provider_config in config.model_providers.items():
        if provider_config.type != PROVIDER_TYPE:
            raise ValueError(f"unsupported provider type {provider_config.type!r} for {name!r}")

    provider_clients: dict[str, httpx2.AsyncClient] = {}
    if providers is None:
        built: dict[str, ModelProvider] = {}
        for name, provider_config in config.model_providers.items():
            # One client per provider, not the shared one. Sharing means sharing the connection pool, and two providers resolving to the same origin — which two accounts of the same subscription type do — then ride the same TCP connections: a GOAWAY earned by one account's traffic ends the other's in-flight streams. `max_streams_per_connection` does not help, because it bounds how many requests share a connection rather than whose. Spec §8.1.
            #
            # `warn_about_proxies=False`: `build_http_client` reports unusable SOCKS proxies, and that report is about the environment rather than about this provider. Left on, it would repeat verbatim once per provider on top of the caller's own.
            client = build_http_client(config, proxy_from_cli=proxy_from_cli, warn_about_proxies=False)
            provider_clients[name] = client
            # Per provider: each may name its own token file.
            token_source = build_github_token_source(config, name)
            ghc_config = GhcClientConfig(
                api_base_url_override=provider_config.api_base_url,
                auth_base_url_override=provider_config.auth_base_url,
            )
            token_manager = CopilotTokenManager(
                token_source,
                client,
                auth_base_url=ghc_config.auth_base_url,
                identity_headers=build_identity_headers(ghc_config),
            )
            built[name] = build_copilot_provider(
                name,
                config,
                http_client=client,
                token_manager=token_manager,
                interaction_id=interaction_id,
            )
        providers = built

    # Static mapping checks, here rather than after `refresh_catalogs` because none of them consults a catalog — that is exactly the property the user's ruling selected for. Warned, never raised: a typo'd qualifier still leaves every other model routable, and failing start-up over it was explicitly ruled against. Spec §5.1.
    for problem in inspect_mappings(
        config.model_mappings,
        frozenset(config.model_providers),
        fallback=config.fallback_model_provider,
    ):
        logger.warning("model_mappings %s: %s", problem.kind, problem.detail)

    # The built-ins go into whatever registry the caller brought, so their order is resolved together with anything a caller added rather than in a second, separate pass.
    subscriber_registry = subscribers if subscribers is not None else SubscriberRegistry[RequestContext]()
    # Each provider's own patterns, kept apart rather than merged. The key lives under `model_providers.<name>` because the answer is that provider's, and a merge lets a provider whose list is empty inherit every other provider's — passing a gate its own configuration never opened.
    #
    # Compiled here rather than per request, which also puts a pattern that does not compile at startup — in the config's own words — instead of inside whichever request first reached the gate.
    web_search_models = compile_supported_by_provider(
        {name: provider.models_support_web_search for name, provider in config.model_providers.items()}
    )
    # `proxied` is a spelling `config.example.yaml` defines and this project has not built: it asks the proxy to strip the client's breakpoints and inject its own, and only the stripping half exists. Refusing at startup rather than treating it as `passthrough`, because the quiet version of this is an operator who configured the proxy to own prompt caching, sees no error, and is billed as though nobody owned it. A config value that cannot be honoured belongs in the same class as a pattern that does not compile — it stops start-up, not the first request that reaches it.
    if config.hook_fix_anthropic_request.cache_control == "proxied":
        raise ValueError(
            "hook_fix_anthropic_request.cache_control: 'proxied' is not implemented "
            "(it would inject the proxy's own breakpoints; only stripping exists). "
            "Use 'sanitize' to remove keys this upstream refuses, 'passthrough' to forward as-is, "
            "or 'disabled' to send no cache_control at all."
        )

    register_builtin_subscribers(
        subscriber_registry,
        web_search_models=web_search_models,
        web_search_enabled=config.model_translation.to_openai_responses.hosted_web_search,
        default_provider=resolve_default_name(config),
        # Keyed on the resolved model id, which is the name upstream receives. Passed straight through rather than pre-processed: unlike the web-search patterns there is nothing to compile, and the only thing that could be checked here — whether the value is an effort the model publishes — is a question about the live catalog rather than about the config, so it is answered per request.
        thinking_efforts=config.model_thinking_effort,
        thinking_display=config.hook_fix_anthropic_request.thinking.display,
        cache_control=config.hook_fix_anthropic_request.cache_control,
        # Compiled here rather than per request, for the same reason as the beta table above it: a pattern that does not compile should stop start-up, in the config's own words, rather than raise from inside whichever request first reached it.
        cache_control_sanitize=compile_sanitize_table(
            config.hook_fix_anthropic_request.cache_control_sanitize
        ),
    )

    return Chain(
        config=config,
        beta_flag_denials=compile_beta_flag_denials(
            config.hook_strip_anthropic_request_headers.strip_anthropic_beta_flags
        ),
        providers=ProviderRegistry(
            providers,
            default=default_name,
            fallback=config.fallback_model_provider,
        ),
        translators=default_registry(config.model_translation),
        subscribers=subscriber_registry.freeze(),
        http_client=http_client,
        provider_clients=provider_clients,
        # One limiter per provider: a limit on one upstream must not throttle another.
        rate_limiters={name: RateLimiter(config.reactive_rate_limiter) for name in providers},
    )


async def refresh_catalogs(chain: Chain) -> None:
    """Populate every provider's catalog, letting one provider's failure be one provider's failure.

    Routing fails closed on capability, so an empty catalog rejects every request until this runs.

    **Each provider is refreshed inside its own guard, and that is not defensive padding.** `refresh_catalog` raises when a token file is missing or upstream is unreachable; `chain.providers.names` is a `frozenset`, so iteration order comes from hashing rather than from anything an operator chose; and this runs exactly once — `run_model_refresh_loop` has no caller and `model_refresh_interval` has no consumer on this chain, so nothing retries. Ungurded, a secondary provider with a stale token could end the loop before the **default** provider was ever refreshed, and `/health/readiness` would then answer 503 for the entire life of the process while the account that serves almost all traffic sat there healthy. Measured 2026-08-27 with a two-provider configuration: whether the default loaded depended on which name the set happened to yield first.

    That failure would also have contradicted the ruling behind `_is_ready`. Spec §4.3 chose "the default provider has a catalogue" over `all(...)` on the grounds that a secondary provider going down is a degradation rather than an outage — true of routing, and false of loading until this guard existed.

    Sorted rather than in set order: the guard is what makes order stop mattering, but leaving a start-up sequence that varies between runs of the same deployment is not worth the line it saves. The sibling loop in `resolve_provider_base_urls` already had both properties.

    No headers parameter: each provider authenticates its own refresh from its own token manager. One taken from a caller would be captured once and expire, and having the parameter at all suggested authentication was the caller's job when nothing was in fact supplying it.
    """
    for name in sorted(chain.providers.names):
        try:
            await chain.providers.get(name).refresh_catalog()
        except Exception as error:
            # Reported and stepped over, not swallowed: an unloaded catalogue is already visible as `catalog: "empty"` in `/api/status` and as `serviceable: "unknown"` on every route that names this provider, and readiness answers for the default provider on its own. What must not happen is one provider's credentials deciding whether any other provider gets loaded.
            logger.warning("model provider %r: catalog refresh failed: %s", name, error)


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
    "resolve_provider_base_urls",
    "transport_options",
]
