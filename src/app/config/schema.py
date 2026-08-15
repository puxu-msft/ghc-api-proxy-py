"""Configuration schema matching `docs/.human-controlled/config.example.yaml`.

Snapshots are frozen: hot reload swaps the whole tree rather than mutating fields.
A request that started under one version keeps seeing it.

`NOT_HOT_RELOADABLE` lists the dotted paths the spec marks as requiring a restart.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type TlsMode = bool | Literal["both"]
type CountTokensProvider = Literal["ghc", "local"]
type BufferingPolicy = Literal["block", "until-tool-use", "full"]
type CacheControlMode = Literal["disabled", "passthrough", "sanitize", "proxied"]
type CacheTtl = Literal["5m", "1h"]
type ContextEditingMode = bool | Literal["clear-thinking", "clear-tooluse", "clear-both"]
type AssistantMessageLayout = bool | Literal["move_and_synthetic", "synthetic_only"]
type ContentBlockStartCompat = bool | Literal["signature_delta", "redacted_thinking"]
type RefusalAction = Literal["passthrough", "as_end_turn", "as_error"]

# Dotted paths the spec marks as requiring a restart. Everything else is hot-reloadable.
NOT_HOT_RELOADABLE = frozenset(
    {
        "model_providers.*.base_url",
        "pidfile",
        "proxy",
        "rate_limiter",
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
    tls: TlsConfig = Field(default_factory=TlsConfig)


class CountTokensConfig(Section):
    providers: list[CountTokensProvider] = Field(default_factory=lambda: ["ghc", "local"])
    max_retries: int = Field(default=2, ge=0)


class InboundConfig(Section):
    anthropic_count_tokens: CountTokensConfig = Field(default_factory=CountTokensConfig)


class ModelProviderConfig(Section):
    type: Literal["github_copilot"]
    base_url: str = ""
    model_refresh_interval: int = Field(default=3600, ge=0)
    disabled_models: list[str] = Field(default_factory=lambda: list[str]())


class UpstreamTransportConfig(Section):
    tcp_keepalive_interval: int = Field(default=15, ge=0)
    http2_ping_interval: int = Field(default=15, ge=0)


class UpstreamRequestTimeoutsConfig(Section):
    # 0 disables each terminator.
    # The spec's frozen invariant is never to false-kill legitimate thinking.
    # Silence on a live connection has no provably safe wall-clock bound.
    response_header: int = Field(default=0, ge=0)
    response_header_overrides: dict[str, int] = Field(default_factory=lambda: dict[str, int]())
    stream_idle: int = Field(default=0, ge=0)
    stream_idle_overrides: dict[str, int] = Field(default_factory=lambda: dict[str, int]())
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


class RateLimiterConfig(Section):
    retry_interval: int = Field(default=10, ge=0)
    request_interval: int = Field(default=10, ge=0)
    recovery_interval: int = Field(default=600, ge=0)
    consecutive_successes: int = Field(default=5, ge=1)


class HedgeConfig(Section):
    threshold_sec: int = Field(default=300, ge=0)
    max_secondary_candidates: int = Field(default=1, ge=0)


class ClientDeliveryConfig(Section):
    # Measured from admission and never reset by retries, so it bounds the whole operation.
    # Also the base for the systemd stop timeout.
    client_request_deadline: int = Field(default=3600, ge=0)
    buffering_policy: BufferingPolicy = "block"
    buffer_cap_bytes: int = Field(default=16_777_216, ge=0)
    synthesized_response_headers_after_sec: int = Field(default=240, ge=0)
    sse_ping_interval: int = Field(default=15, ge=0)
    hedge: HedgeConfig = Field(default_factory=HedgeConfig)


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
    strip_system_reminder_from_Read: bool = False


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
    rate_limiter: RateLimiterConfig = Field(default_factory=RateLimiterConfig)
    client_delivery: ClientDeliveryConfig = Field(default_factory=ClientDeliveryConfig)

    hook_strip_anthropic_request_headers: StripRequestHeadersHook = Field(
        default_factory=StripRequestHeadersHook
    )
    hook_fix_anthropic_request: FixAnthropicRequestHook = Field(
        default_factory=FixAnthropicRequestHook
    )
    hook_fix_anthropic_sse: FixAnthropicSseHook = Field(default_factory=FixAnthropicSseHook)

    model_config = ConfigDict(frozen=True, extra="forbid")
