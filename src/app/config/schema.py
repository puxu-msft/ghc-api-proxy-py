"""Configuration schema matching `docs/.human-controlled/config.example.yaml`.

Snapshots are frozen: hot reload swaps the whole tree rather than mutating fields.
A request that started under one version keeps seeing it.

`NOT_HOT_RELOADABLE` lists the dotted paths the spec marks as requiring a restart.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

type TlsMode = bool | Literal["both"]
type CountTokensProvider = Literal["ghc", "local"]
type BufferingPolicy = Literal["block", "until-tool-use", "full"]
type CacheControlMode = Literal["disabled", "passthrough", "sanitize", "proxied"]
type CacheTtl = Literal["5m", "1h"]
type ContextEditingMode = bool | Literal["clear-thinking", "clear-tooluse", "clear-both"]
# `bool` would accept `true`, which the spec does not define; only `false` carries meaning.
type AssistantMessageLayout = Literal[False, "move_and_synthetic", "synthetic_only"]
type ContentBlockStartCompat = Literal[False, "signature_delta", "redacted_thinking"]
type RefusalAction = Literal["passthrough", "as_end_turn", "as_error"]
# One value today. Named so the seam exists before the second placement does; `as-role-system`
# would put the system prompt at the head of the conversation instead.
type SystemPromptPlacement = Literal["instructions-joint-string"]

# Dotted paths the spec marks as requiring a restart. Everything else is hot-reloadable.
#
# `server.host` / `server.port` carry no such note, but nothing rebinds a live listener.
# lifecycle.md realises a port change by starting a new process on the same port.
# Leaving them reloadable would make `current` report a port nobody listens on.
# They are pinned and reported as restart-required rather than silently applied.
NOT_HOT_RELOADABLE = frozenset(
    {
        "model_providers.*.api_base_url",
        "model_providers.*.auth_base_url",
        "model_providers.*.github_token_file",
        "pidfile",
        "proxy",
        "reactive_rate_limiter",
        "server.host",
        "server.port",
        "upstream_request_retry.max_total",
    }
)


class Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TlsConfig(Section):
    # false = HTTP only, true = HTTPS only, "both" = same port, dispatched on the first byte.
    mode: TlsMode = False
    cert: str = ""
    key: str = ""
    strict: bool = False


class ServerConfig(Section):
    # Localhost-only by default; the port deliberately differs from the Bun service on 4141.
    host: str = "127.0.0.1"
    port: int = Field(default=4142, ge=1, le=65535)
    tls: TlsConfig = Field(default_factory=TlsConfig)


class CountTokensConfig(Section):
    providers: list[CountTokensProvider] = Field(default_factory=lambda: ["ghc", "local"])
    max_retries: int = Field(default=2, ge=0)


class InboundConfig(Section):
    anthropic_count_tokens: CountTokensConfig = Field(default_factory=CountTokensConfig)


class ModelProviderConfig(Section):
    type: Literal["github_copilot"]
    # Where inference goes.
    api_base_url: str = ""
    # Where a GitHub token is exchanged for a Copilot one, and where the account is described.
    # A separate host from the one above, and separately configurable: an enterprise install moves
    # both, and leaving this one a module constant meant nothing could be stood up locally — the
    # inference calls could be redirected and the three auth calls could not.
    auth_base_url: str = ""
    # May contain `$XDG_DATA_HOME`; expanded by `app.config.paths.expand_user_path`.
    github_token_file: str = ""
    model_refresh_interval: int = Field(default=3600, ge=0)
    disabled_models: list[str] = Field(default_factory=lambda: list[str]())
    # Which models actually execute hosted web search, matched exactly against upstream `model.id`
    # as `disabled_models` is. A declaration from the client is translated into this endpoint's own
    # `{"type": "web_search"}` only for a model named here; for any other it is removed, and the
    # turn goes on without the capability.
    #
    # Maintained by hand because the catalog cannot answer the question. Measured 2026-08-20 across
    # the live catalog — 42 models, 67,656 bytes — the union of `capabilities.supports` keys holds
    # no web-search bit of any kind, and a value-level scan for `search|web_|builtin|hosted` over
    # the whole document returns nothing. The two models known to work cannot be told apart from
    # the rest on any advertised field.
    #
    # The default is the catalog's OpenAI-vendor models that advertise `/responses`, as of that
    # date. Taken by `vendor` rather than by a `gpt-` name prefix, which would sweep in `gpt-5-mini`
    # — vendor `Azure OpenAI`, a different supply chain. Only `gpt-5.5` and `gpt-5.6-sol` have
    # actually been put to upstream; the rest are inferred from sharing a vendor with them, and
    # `gpt-5.3-codex` is the most doubtful of those.
    #
    # Both ways of being wrong show up, and neither is silent. A model listed here that cannot
    # search answers 400 and says which value it refused. A model left out that could search has
    # its declaration removed, which is reported at INFO with the model named. Expect this list to
    # drift as the catalog does.
    models_support_web_search: list[str] = Field(
        default_factory=lambda: [
            "gpt-5.3-codex",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.5",
            "gpt-5.6-luna",
            "gpt-5.6-sol",
            "gpt-5.6-terra",
        ]
    )


class UpstreamTransportConfig(Section):
    tcp_keepalive_interval: int = Field(default=15, ge=0)
    # Set false to negotiate HTTP/1.1 upstream. Ruled 2026-08-20, after one upstream GOAWAY killed every in-flight stream at once: HTTP/2 multiplexes them onto one connection, so one connection-level event is one blast radius. HTTP/1.1 gives each request its own connection and costs more handshakes. See `docs/agents/upstream-h2-goaway/findings.md`.
    # Authoritative on its own. It used to be derived from `http2_ping_interval > 0`, which meant a key named after a ping interval silently decided the protocol.
    http2: bool = True
    # NOT IMPLEMENTED by the current transport, and kept rather than deleted because it is a user-authored key with a spec behind it. httpx 0.28.1 / httpcore 1.0.9 expose no HTTP/2 PING interval to configure, so nothing reads this value today. It does not disable HTTP/2 — `http2` above does.
    http2_ping_interval: int = Field(default=15, ge=0)


class UpstreamRequestTimeoutsConfig(Section):
    # 0 disables each terminator.
    # The spec's frozen invariant is never to false-kill legitimate thinking.
    # Silence on a live connection has no provably safe wall-clock bound.
    response_header: int = Field(default=0, ge=0)
    response_header_overrides: dict[str, int] = Field(default_factory=lambda: dict[str, int]())
    stream_idle: int = Field(default=0, ge=0)
    # Constrained on the value, not just the key: the scalar above already refuses a negative, and without the same bound here a negative override passes validation and then reads as `<= 0` at the guard — which means "disabled". An operator who mistypes the sign gets the opposite of what they asked for, silently.
    stream_idle_overrides: dict[str, Annotated[int, Field(ge=0)]] = Field(
        default_factory=lambda: dict[str, int]()
    )
    upstream_request_deadline: int = Field(default=1200, ge=0)


class RetryStrategyConfig(Section):
    max_retries: int = Field(default=0, ge=0)


class ContinuationStrategyConfig(Section):
    enabled: bool = True
    max_retries: int = Field(default=10, ge=0)
    message: str = "Please continue where you left off."


class RetryStrategiesConfig(Section):
    githubTokenExpired: RetryStrategyConfig = Field(
        default_factory=lambda: RetryStrategyConfig(max_retries=0)
    )
    network: RetryStrategyConfig = Field(
        default_factory=lambda: RetryStrategyConfig(max_retries=9)
    )
    serverError: RetryStrategyConfig = Field(
        default_factory=lambda: RetryStrategyConfig(max_retries=9)
    )
    streamReplay: RetryStrategyConfig = Field(
        default_factory=lambda: RetryStrategyConfig(max_retries=100)
    )
    continuation: ContinuationStrategyConfig = Field(
        default_factory=ContinuationStrategyConfig
    )


class UpstreamRequestRetryConfig(Section):
    max_total: int = Field(default=20, ge=0)
    strategies: RetryStrategiesConfig = Field(default_factory=RetryStrategiesConfig)
    max_tokens_as_retryable: bool = True


class ProactiveRateLimiterConfig(Section):
    """The bound that replaced byte-level memory accounting.

    Ruled 2026-08-19. 50 is a ceiling for a pathological client, not a throttle: real traffic is
    429 requests across a whole day. A request over the limit waits rather than being refused —
    see `app.server.admission` for why refusing is worse than waiting.
    """

    # 0 disables the gate.
    max_inflight: int = Field(default=50, ge=0)


class ReactiveRateLimiterConfig(Section):
    """Engaged only by an upstream 429 or 502, per the spec.

    503 and 504 stay with ordinary retry, so a slow upstream does not become a rate limit.
    """

    retry_interval: int = Field(default=10, ge=0)
    request_interval: int = Field(default=10, ge=0)
    recovery_interval: int = Field(default=600, ge=0)
    consecutive_successes: int = Field(default=5, ge=1)


class HedgeConfig(Section):
    threshold_sec: int = Field(default=300, ge=0)
    max_secondary_candidates: int = Field(default=1, ge=0)


class ToOpenAiResponsesConfig(Section):
    """How an Anthropic request is shaped for the Responses endpoint."""

    # Where the system prompt goes. `instructions-joint-string` puts the blocks in the top-level
    # `instructions` as one `\n\n`-joined string, which is the only form this upstream accepts
    # today. Kept as a named setting rather than baked in so a second placement — `as-role-system`,
    # a `role: system` message at the head of the conversation — can be added without the caller
    # changing.
    system_prompts: SystemPromptPlacement = "instructions-joint-string"


class ModelTranslationConfig(Section):
    to_openai_responses: ToOpenAiResponsesConfig = Field(
        default_factory=ToOpenAiResponsesConfig
    )


class ClientDeliveryConfig(Section):
    # Measured from admission and never reset by retries, so it bounds the whole operation.
    # Also the base for the systemd stop timeout.
    client_request_deadline: int = Field(default=3600, ge=0)
    buffering_policy: BufferingPolicy = "block"
    buffer_cap_bytes: int = Field(default=16_777_216, ge=0)
    synthesized_response_headers_after_sec: int = Field(default=240, ge=0)
    sse_ping_interval: int = Field(default=15, ge=0)
    hedge: HedgeConfig = Field(default_factory=HedgeConfig)


class HistoryConfig(Section):
    enabled: bool = True


class HooksConfig(Section):
    """Subscription points the spec names, each listing the hooks to run there.

    These are the operator-facing points, not the driver's internal `attempt.*`/`request.*` events.
    Order within a list is the order given.
    """

    on_client_request_parsed: list[str] = Field(default_factory=lambda: list[str]())
    on_upstream_request_ready: list[str] = Field(default_factory=lambda: list[str]())
    on_upstream_sse_block_ready: list[str] = Field(default_factory=lambda: list[str]())
    on_client_sse_block_ready: list[str] = Field(default_factory=lambda: list[str]())
    on_upstream_request_closed: list[str] = Field(default_factory=lambda: list[str]())
    on_client_request_closed: list[str] = Field(default_factory=lambda: list[str]())


class StripRequestHeadersHook(Section):
    strip_attribution_header: bool = True
    beta_strip_headers: dict[str, list[str]] = Field(
        default_factory=lambda: dict[str, list[str]]()
    )


class ExtendedCacheTtlConfig(Section):
    enabled: bool = False
    tools_system_ttl: CacheTtl = "1h"
    messages_ttl: CacheTtl = "5m"


class ContextEditingConfig(Section):
    # YAML 1.1 parses a bare `off` as boolean false, so the disabled state is the bool.
    enabled: ContextEditingMode = False
    trigger: int = Field(default=100_000, ge=0)
    keep_tools: int = Field(default=3, ge=0)
    keep_thinking: int = Field(default=1, ge=0)


class StripAllThinkingOnRejectConfig(Section):
    enabled: bool = True
    poisoned_ttl_minutes: int = Field(default=4320, ge=0)


class RequestThinkingConfig(Section):
    assistant_message_layout: AssistantMessageLayout = "move_and_synthetic"
    strip_both_empty_thinking_blocks: bool = True
    strip_all_thinking_blocks_on_reject: StripAllThinkingOnRejectConfig = Field(
        default_factory=StripAllThinkingOnRejectConfig
    )


class FixAnthropicRequestHook(Section):
    cache_control: CacheControlMode = "passthrough"
    extended_cache_ttl: ExtendedCacheTtlConfig = Field(default_factory=ExtendedCacheTtlConfig)
    context_editing: ContextEditingConfig = Field(default_factory=ContextEditingConfig)
    thinking: RequestThinkingConfig = Field(default_factory=RequestThinkingConfig)


class SseThinkingConfig(Section):
    content_block_start_compat: ContentBlockStartCompat = "signature_delta"


class RewriteRefusalConfig(Section):
    action: RefusalAction = "as_end_turn"
    text: str = "Please rephrase your request with a more safe statement."


class FixAnthropicSseHook(Section):
    thinking: SseThinkingConfig = Field(default_factory=SseThinkingConfig)
    fix_malformed_unicode_escape: bool = True
    rewrite_refusal: RewriteRefusalConfig = Field(default_factory=RewriteRefusalConfig)


class ProxyConfig(Section):
    server: ServerConfig = Field(default_factory=ServerConfig)
    inbound: InboundConfig = Field(default_factory=InboundConfig)

    # The sole source of model-name mapping; the spec forbids built-in defaults.
    model_mappings: dict[str, str] = Field(default_factory=lambda: dict[str, str]())

    model_translation: ModelTranslationConfig = Field(default_factory=ModelTranslationConfig)

    model_providers: dict[str, ModelProviderConfig] = Field(
        default_factory=lambda: dict[str, ModelProviderConfig]()
    )
    default_model_provider: str = ""

    pidfile: str = ""
    graceful_cleanup_timeout: int = Field(default=60, ge=0)
    proxy: str = ""

    upstream_transport: UpstreamTransportConfig = Field(
        default_factory=UpstreamTransportConfig
    )
    upstream_request_timeouts: UpstreamRequestTimeoutsConfig = Field(
        default_factory=UpstreamRequestTimeoutsConfig
    )
    upstream_request_retry: UpstreamRequestRetryConfig = Field(
        default_factory=UpstreamRequestRetryConfig
    )
    proactive_rate_limiter: ProactiveRateLimiterConfig = Field(
        default_factory=ProactiveRateLimiterConfig
    )
    reactive_rate_limiter: ReactiveRateLimiterConfig = Field(
        default_factory=ReactiveRateLimiterConfig
    )
    client_delivery: ClientDeliveryConfig = Field(default_factory=ClientDeliveryConfig)

    history: HistoryConfig = Field(default_factory=HistoryConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)

    hook_strip_anthropic_request_headers: StripRequestHeadersHook = Field(
        default_factory=StripRequestHeadersHook
    )
    hook_fix_anthropic_request: FixAnthropicRequestHook = Field(
        default_factory=FixAnthropicRequestHook
    )
    hook_fix_anthropic_sse: FixAnthropicSseHook = Field(default_factory=FixAnthropicSseHook)

    model_config = ConfigDict(frozen=True, extra="forbid")
