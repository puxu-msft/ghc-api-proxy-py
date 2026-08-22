from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import EnvSettingsSource

from app.config.loading import ENV_PREFIX, NO_WHOLE_VALUE_FROM_ENVIRONMENT
from app.graceful_timeout import DEFAULT_GRACEFUL_TIMEOUT_SECONDS


class EnvSourceWithoutWholeValues(EnvSettingsSource):
    """The environment source, with the flat spelling of a few settings removed.

    Dropped by variable name rather than by settings key, because the two spellings arrive as the same key: `GHC_API_PROXY_MODEL_MAPPINGS` and `GHC_API_PROXY_MODEL_MAPPINGS__GPT` both land on `model_mappings`, and only the first is the one being refused.

    Filtering where `load_settings` assembles its layers is not enough, and that is worth stating because it looks like it should be: `BaseSettings` runs its own environment source during validation, and that source wins over the values passed in — `AppSettings.model_validate({"model_mappings": {}})` still came back holding whatever the environment said. So the exclusion has to be made here, on the source itself.
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        refused = {f"{ENV_PREFIX}{name}".lower() for name in NO_WHOLE_VALUE_FROM_ENVIRONMENT}
        self.env_vars = {
            name: value for name, value in self.env_vars.items() if name not in refused
        }


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class UpstreamConfig(FrozenModel):
    type: Literal["copilot", "generic"] = "copilot"
    ghc_api_base_url: str = ""
    openai_base_url: str = ""
    anthropic_base_url: str = ""
    api_key: str = ""
    auth_type: Literal["bearer", "x-api-key"] = "bearer"
    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry: int = 30
    connect_timeout: float = 10.0
    read_timeout: float = 300.0
    http2: bool = True
    proxy: str | None = None


class AuthConfig(FrozenModel):
    github_token: str = ""
    account_type: Literal["individual", "business", "enterprise", "self-hosted"] | None = None
    token_file: str = ""
    show_github_token: bool = False


class HeadersConfig(FrozenModel):
    vscode_version: str = "1.104.3"
    copilot_version: str = "0.38.0"
    api_version: str = "2025-05-01"


class ApprovalConfig(FrozenModel):
    enabled: bool = False
    timeout_seconds: float = 300.0


class HistoryConfig(FrozenModel):
    enabled: bool = True
    success_limit: int = 50
    failure_limit: int = 200
    reaper_interval: int = 600
    db_path: str = ""
    websocket: bool = True


class RateLimiterConfig(FrozenModel):
    enabled: bool = True
    retry_interval: int = 10
    request_interval: int = 10
    recovery_interval: int = 600
    consecutive_successes: int = 5


class TimeoutConfig(FrozenModel):
    stream_idle: int = 300
    stream_idle_overrides: dict[str, int] = Field(
        default_factory=lambda: {"gpt-5.5": 600}
    )
    response_header: int = 300
    response_header_overrides: dict[str, int] = Field(default_factory=dict)
    stale_request_max_age: int = 600
    request_deadline: int = 0


class AnthropicConfig(FrozenModel):
    route_override: Literal["auto", "messages", "responses"] = "auto"
    use_upstream_count_tokens: bool = True
    effort_overrides: dict[str, list[str]] = Field(default_factory=dict)
    beta_strip_headers: dict[str, list[str]] = Field(default_factory=dict)
    stream_keepalive_ping_sec: int = 20
    stream_keepalive_mode: Literal["ping", "empty_text"] = "empty_text"
    stream_commit_after_sec: int = 20
    thinking_block_message_policy: Literal["preserve", "stripped"] = "preserve"
    thinking_block_sanitize: str = "all_empty"
    thinking_destack_strategy: Literal["passthrough", "insert_text", "move_blocks"] = "move_blocks"
    poisoned_thinking_quarantine: bool = True
    poisoned_thinking_ttl_hours: float = 72
    tool_search: bool = True
    tool_search_non_deferred: list[str] = Field(default_factory=list)
    warmup: Literal["allow", "reject", "drop", "fake"] = "allow"
    strict_request_headers: bool = False
    strict_response_headers: bool = False
    request_header_blacklist: list[str] = Field(
        default_factory=lambda: ["x-anthropic-billing-header"]
    )
    request_header_whitelist: list[str] = Field(
        default_factory=lambda: [
            "accept",
            "anthropic-dangerous-direct-browser-access",
            "x-app",
            "x-claude-code-*",
            "x-stainless-*",
        ]
    )
    response_header_blacklist: list[str] = Field(default_factory=list)
    response_header_whitelist: list[str] = Field(
        default_factory=lambda: [
            "request-id",
            "x-request-id",
            "anthropic-ratelimit-*",
            "anthropic-organization-id",
            "retry-after",
        ]
    )


class ObservabilityConfig(FrozenModel):
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "text"] = "text"
    tracing_enabled: bool = False
    tracing_endpoint: str = ""
    tui_enabled: bool = False


class ResponsesConfig(FrozenModel):
    normalize_call_ids: bool = True
    upstream_ws: bool = False
    ws_queue_size: int = Field(default=32, ge=1)
    max_ws_frame_bytes: int = 0
    max_client_ws_connections: int = 256
    max_upstream_ws_connections: int = 32


class TokenizationConfig(FrozenModel):
    state_path: str = ""
    snapshot_root: str = ""
    flush_interval: float = Field(default=5.0, gt=0)


class HooksConfig(FrozenModel):
    modules: list[str] = Field(default_factory=list)
    disabled: list[str] = Field(default_factory=list)
    timeout_ms: int = Field(default=5_000, ge=1)
    deduplicate_tool_calls: bool = False


class ShutdownConfig(FrozenModel):
    graceful_timeout: int = Field(
        default=DEFAULT_GRACEFUL_TIMEOUT_SECONDS,
        ge=1,
    )
    drain_timeout: int = Field(default=0, ge=0)


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GHC_API_PROXY_",
        env_nested_delimiter="__",
        case_sensitive=False,
        frozen=True,
        extra="forbid",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        del env_settings  # Replaced rather than reordered; see the source's own docstring.
        return (
            init_settings,
            EnvSourceWithoutWholeValues(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )

    host: str = "127.0.0.1"
    port: int = Field(default=4141, ge=1, le=65535)
    debug: bool = False
    upstream: UpstreamConfig = Field(default_factory=UpstreamConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    headers: HeadersConfig = Field(default_factory=HeadersConfig)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)
    history: HistoryConfig = Field(default_factory=HistoryConfig)
    rate_limiter: RateLimiterConfig = Field(default_factory=RateLimiterConfig)
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)
    anthropic: AnthropicConfig = Field(default_factory=AnthropicConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    openai_responses: ResponsesConfig = Field(default_factory=ResponsesConfig)
    tokenization: TokenizationConfig = Field(default_factory=TokenizationConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    shutdown: ShutdownConfig = Field(default_factory=ShutdownConfig)
    model_overrides: dict[str, str] = Field(
        default_factory=lambda: {
            "opus": "claude-opus-4.6",
            "sonnet": "claude-sonnet-4.6",
            "haiku": "claude-haiku-4.5",
        }
    )
    model_mappings: dict[str, str] = Field(default_factory=dict)
    disabled_models: list[str] = Field(default_factory=list)
    sanitize_tool_names: bool = False
    model_refresh_interval: int = 600
