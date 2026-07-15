from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    account_type: Literal["individual", "business", "enterprise"] = "individual"
    token_file: str = ""
    show_github_token: bool = False


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
    upstream_keepalive: int = 15
    upstream_h2_ping: int = 15
    stale_request_max_age: int = 600
    request_deadline: int = 0


class AnthropicConfig(FrozenModel):
    effort_overrides: dict[str, list[str]] = Field(default_factory=dict)
    beta_strip_headers: dict[str, list[str]] = Field(default_factory=dict)
    stream_keepalive_ping_sec: int = 20
    stream_keepalive_mode: Literal["ping", "empty_text"] = "empty_text"
    stream_commit_after_sec: int = 20


class ObservabilityConfig(FrozenModel):
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "text"] = "text"
    tracing_enabled: bool = False
    tracing_endpoint: str = ""
    tui_enabled: bool = False


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GHC_",
        env_nested_delimiter="__",
        case_sensitive=False,
        frozen=True,
        extra="forbid",
    )

    host: str = "127.0.0.1"
    port: int = Field(default=4141, ge=1, le=65535)
    debug: bool = False
    upstream: UpstreamConfig = Field(default_factory=UpstreamConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)
    history: HistoryConfig = Field(default_factory=HistoryConfig)
    rate_limiter: RateLimiterConfig = Field(default_factory=RateLimiterConfig)
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)
    anthropic: AnthropicConfig = Field(default_factory=AnthropicConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
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