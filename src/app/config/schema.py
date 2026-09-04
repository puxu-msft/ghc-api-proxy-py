"""Configuration schema matching `docs/.human-controlled/config.example.yaml`.

Snapshots are frozen: hot reload swaps the whole tree rather than mutating fields.
A request that started under one version keeps seeing it.

`NOT_HOT_RELOADABLE` lists the dotted paths the spec marks as requiring a restart.
"""

from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

type TlsMode = bool | Literal["both"]
# The name of the local estimator leg. Everything else in `inbound.anthropic_count_tokens.providers` is a `model_providers` key.
LOCAL_COUNTER = "local"
type BufferingPolicy = Literal["block", "until-tool-use", "full"]
type CacheControlMode = Literal["disabled", "passthrough", "sanitize", "proxied"]
type CacheTtl = Literal["5m", "1h"]
type ContextEditingMode = bool | Literal["clear-thinking", "clear-tooluse", "clear-both"]
# `bool` would accept `true`, which the spec does not define; only `false` carries meaning.
type AssistantMessageLayout = Literal[False, "move_and_synthetic", "synthetic_only"]
type ContentBlockStartCompat = Literal[False, "signature_delta", "redacted_thinking"]
type RefusalAction = Literal["passthrough", "as_end_turn", "as_error"]
# One value today. Named so the seam exists before the second placement does; `as-role-system` would put the system prompt at the head of the conversation instead.
type SystemPromptPlacement = Literal["instructions-joint-string"]
# What to do when a web search declaration carries a domain restriction this upstream has no parameter for. Measured: `allowed_domains` and `blocked_domains` each earn `Unknown parameter`, so they cannot be sent under any spelling, and the only question is what to do instead.
type WebSearchConstraintPolicy = Literal["error", "drop_fields"]
# What to do with a Claude Code auto mode authorisation request. `passthrough` forwards it upstream like anything else; the other two answer it here with a fixed decision and never call upstream at all.
# Spelled out rather than using `false` for the disabled state, per `config.example.yaml`. The bool spelling that `assistant_message_layout` and `context_editing.enabled` use exists to dodge YAML 1.1 reading a bare `off` as boolean false; `passthrough` is not a word that trap applies to, so it can say what it means.
type AutoModeDecision = Literal["passthrough", "allow", "block"]
# What to do with `thinking.display` on the way to an Anthropic Messages upstream. `passthrough` — the default — sends whatever the client said and adds nothing; `drop` removes the key; the two remaining values rewrite it. `omitted` streams `thinking` blocks with empty text and is the upstream default on the Claude 5 family, `summarized` asks for a readable summary of the reasoning instead.
type ThinkingDisplayPolicy = Literal["passthrough", "drop", "omitted", "summarized"]

# Dotted paths the spec marks as requiring a restart. Everything else is hot-reloadable.
#
# `server.host` / `server.port` carry no such note, but nothing rebinds a live listener.
# lifecycle.md realises a port change by starting a new process on the same port.
# Leaving them reloadable would make `current` report a port nobody listens on.
# They are pinned and reported as restart-required rather than silently applied.
NOT_HOT_RELOADABLE = frozenset(
    {
        "model_providers.*.api_base_url",
        "model_providers.*.app_version",
        "model_providers.*.auth_base_url",
        "model_providers.*.auth_state_file",
        "model_providers.*.client_type",
        "model_providers.*.device_id",
        "model_providers.*.gateway_api_key",
        "model_providers.*.github_token_file",
        "model_providers.*.install_id",
        "model_providers.*.models",
        "model_providers.*.route_target",
        "model_providers.*.type",
        "model_providers.*.user_agent",
        "model_providers.*.x_token",
        "pidfile_dir",
        "proxy",
        "reactive_rate_limiter",
        "server.host",
        "server.port",
        # The outbound client is built once, at startup. Socket options are fixed when a connection is opened, so a reload that accepted these would report a value no live connection is using.
        "upstream_transport.http2",
        "upstream_transport.tcp_keepalive_interval",
        "upstream_request_retry.max_total",
    }
)

# Fields shared with an older provider but fixed into the Xingchen instance at startup. Kept type-scoped so this feature does not silently change the existing GitHub Copilot hot-reload contract.
PROVIDER_NOT_HOT_RELOADABLE: dict[str, frozenset[str]] = {
    "xingchen": frozenset({"disabled_models"}),
}


class Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


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
    """Which legs may answer a token count, in order.

    Each entry is either `local` — this proxy's calibrated estimate — or the name of a configured `model_providers` key. **Not an enumeration.** `ghc` is a legal value because some deployments configure a provider called `ghc`, not because the string is special; pinning the type to `Literal["ghc", "local"]` said that only a deployment whose provider happens to carry that name may ask upstream for a count, which is not a rule anyone made.

    The names are checked against `model_providers` in `ProxyConfig`, because that is where both halves are visible. A check here could only compare against a hard-coded list, which is the thing being removed.
    """

    providers: list[str] = Field(default_factory=lambda: ["ghc", LOCAL_COUNTER])
    max_retries: int = Field(default=2, ge=0)


class InboundConfig(Section):
    anthropic_count_tokens: CountTokensConfig = Field(default_factory=CountTokensConfig)


class _ModelProviderConfigBase(Section):
    # Where inference goes.
    api_base_url: str = ""
    disabled_models: list[str] = Field(default_factory=lambda: list[str]())


class GithubCopilotProviderConfig(_ModelProviderConfigBase):
    type: Literal["github_copilot"]
    # Where a GitHub token is exchanged for a Copilot one, and where the account is described.
    # A separate host from the one above, and separately configurable: an enterprise install moves both, and leaving this one a module constant meant nothing could be stood up locally — the inference calls could be redirected and the three auth calls could not.
    auth_base_url: str = ""
    # May contain `$XDG_DATA_HOME`; expanded by `app.config.paths.expand_user_path`.
    github_token_file: str = ""
    model_refresh_interval: int = Field(default=3600, ge=0)
    # Which models actually execute hosted web search. Each entry is a **regular expression**, matched against upstream `model.id` with `fullmatch` — so a plain id like `gpt-5.5` still means what it says and needs no anchors, while `gpt-5\.\d+.*` covers a family. A declaration from the client is translated into this endpoint's own `{"type": "web_search"}` only for a model some pattern claims. For any other, the request is answered with a failed `web_search_tool_result` rather than sent on without the tool: a search sub-request stripped of its only tool succeeds by answering from memory, and the client labels that reply as search results.
    #
    # Maintained by hand because the catalog cannot answer the question. Measured 2026-08-20 across the live catalog — 42 models, 67,656 bytes — the union of `capabilities.supports` keys holds no web-search bit of any kind, and a value-level scan for `search|web_|builtin|hosted` over the whole document returns nothing. The two models known to work cannot be told apart from the rest on any advertised field.
    #
    # The default covers the `gpt-<major>.<minor>` line for majors 5 through 9, which is every OpenAI-vendor model advertising `/responses` in that catalog — `gpt-5.3-codex`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.5`, and the three `gpt-5.6-*` — and claims their successors as they appear. Ruled a pattern rather than an id list on 2026-08-21, after an id list had to be hand-extended for exactly that reason.
    #
    # **The dot is load-bearing.** `gpt-5-mini` has no dotted minor and is vendor `Azure OpenAI`, a different supply chain; requiring `\.` is what keeps a family pattern from sweeping it in. A two-digit major (`gpt-10.0`) is deliberately not matched: inventing a naming scheme two majors ahead is a guess, and the failure is an operator adding one line, not a wrong answer.
    #
    # Both ways of being wrong show up, and neither is silent. A model claimed here that cannot search answers 400 and says which value it refused. A model no pattern claims has its search answered as failed, which is reported at INFO with the model named.
    models_support_web_search: list[str] = Field(
        default_factory=lambda: [r"gpt-[5-9]\.\d+.*"]
    )


def _canonical_model_name(name: str) -> str:
    # A transcription of `app.pipeline.model_resolution.canonical`; the config layer stays independent of the pipeline, and a cross-layer test keeps the two spellings aligned.
    return name.strip().lower().replace(".", "-")


class XingchenProviderConfig(_ModelProviderConfigBase):
    type: Literal["xingchen"]
    api_base_url: str = "https://agent.teleai.com.cn/superCowork/sapi/api/v1"
    models: list[str] = Field(min_length=1)
    gateway_api_key: str = Field(min_length=1, repr=False)
    x_token: str = Field(min_length=1, repr=False)
    device_id: str = Field(min_length=1)
    install_id: str = Field(min_length=1)
    app_version: str = "2.4.1"
    route_target: str = "ops-gateway"
    client_type: str = "desktop"
    user_agent: str = "super-agent/1.0"

    @field_validator(
        "api_base_url",
        "gateway_api_key",
        "x_token",
        "device_id",
        "install_id",
        "app_version",
        "route_target",
        "client_type",
        "user_agent",
    )
    @classmethod
    def _value_may_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value may not be empty or blank")
        return value

    @field_validator("models")
    @classmethod
    def _models_must_be_distinct_and_addressable(cls, value: list[str]) -> list[str]:
        if any(not model.strip() for model in value):
            raise ValueError("models may not contain an empty or blank id")
        if len(value) != len(set(value)):
            raise ValueError("models may not contain duplicate ids")
        canonical = [_canonical_model_name(model) for model in value]
        if len(canonical) != len(set(canonical)):
            raise ValueError("models may not contain canonically equivalent ids")
        return value


class CodebuddyProviderConfig(_ModelProviderConfigBase):
    type: Literal["codebuddy"]
    # The desktop app's login-state `.info` file, holding the tokens this provider
    # refreshes and writes back. Empty means auto-discovery in the desktop app's
    # own data directory. Restart-pinned with the other credential paths: a live
    # provider was built around the file it was given at startup.
    # May contain `$XDG_DATA_HOME`; expanded by `app.config.paths.expand_user_path`.
    auth_state_file: str = ""


type ModelProviderConfig = Annotated[
    GithubCopilotProviderConfig | XingchenProviderConfig | CodebuddyProviderConfig,
    Field(discriminator="type"),
]


class UpstreamTransportConfig(Section):
    # A real TCP keep-alive: seconds of idle before the first probe, and seconds between probes. 0 disables it. Until 2026-08-20 this key was mapped to httpx's connection-pool idle expiry instead, which never writes a byte to the socket and does not apply at all while a request is in flight — so the name promised liveness the transport never had. Nothing replaces that mapping: pooling is httpx's own business and was never a setting anyone chose.
    # What it can tell you depends on whether a proxy is in the way. TCP keep-alive is per-connection, and a proxy terminates the connection: measured 2026-08-20, our socket's peer is the origin when direct and the proxy when tunnelling through one. So with a proxy configured this probes the hop to the proxy and says nothing about upstream, whose connection is the proxy's to keep.
    tcp_keepalive_interval: int = Field(default=15, ge=0)
    # HTTP/1.1 is the default; set true to enable HTTP/2 upstream. Ruled 2026-09-05 after HTTP/1.1 materially improved the field failure rate and the current HTTP/2 stack reproduced active-stream loss after graceful GOAWAY. This supports the default without claiming HTTP/2 caused every observed 408. See `.dev/docs/delivery-keepalive/spec.md` §3.
    # Authoritative on its own. It used to be derived from `http2_ping_interval > 0`, which meant a key named after a ping interval silently decided the protocol.
    http2: bool = False
    # NOT IMPLEMENTED, and it cannot be from here. `docs/.dev/…/streaming-resilience.md` asked for a periodic HTTP/2 PING because some intermediaries retire a connection on application-level silence, which an L4 keep-alive cannot answer. httpx exposes no such interval; httpcore 1.0.9 never calls h2's `ping()` and runs no background read loop, so there is nothing to hook without forking the transport. Kept rather than deleted because it is a user-authored key with a spec behind it. It does not disable HTTP/2 — `http2` above does. `timeouts.upstream_h2_ping`, the legacy spelling of the same intent, was deleted in favour of this one.
    http2_ping_interval: int = Field(default=15, ge=0)
    # How many concurrent requests may share one upstream connection. 0 = unlimited, which is httpx's own behaviour and what this ran with until 2026-08-20.
    # Bounds the blast radius of a connection-level event: one GOAWAY ends every stream riding that connection, and on 2026-08-20 that was four requests at the same instant. At N, it is at most N.
    # This is a different choice from `http2: false`, not a milder version of it. A capped connection is still HTTP/2 — framing, HPACK, stream-level resets, and whatever the upstream edge does differently for h2. Turning HTTP/2 off gives that up. Measured evidence for both is in `.dev/docs/upstream/h2-goaway/findings.md`.
    # Left off by default because no measurement here supports a particular number, and one invented would be a decision the operator did not ask to make. Two facts for whoever picks one: upstream advertises `MAX_CONCURRENT_STREAMS = 100`, so only this cap binds; and the sibling service ships 1.
    max_streams_per_connection: int = Field(default=0, ge=0)


class UpstreamRequestTimeoutsConfig(Section):
    # 0 disables each terminator.
    # The user's frozen invariant is never to false-kill legitimate thinking.
    # Silence on a live connection has no provably safe wall-clock bound.
    response_header: int = Field(default=0, ge=0)
    stream_idle: int = Field(default=0, ge=0)
    upstream_request_deadline: int = Field(default=1200, ge=0)


class RetryStrategyConfig(Section):
    max_retries: int = Field(default=0, ge=0)


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


class UpstreamRequestRetryConfig(Section):
    max_total: int = Field(default=20, ge=0)
    strategies: RetryStrategiesConfig = Field(default_factory=RetryStrategiesConfig)
    # Which upstream stop reasons mean "this turn can be carried on", and so get handed back to the client as a tool call rather than simply ending.
    #
    # The same list decides whether a block upstream cut short may be dropped. Those two are one setting on purpose: dropping content is only defensible when the client is handed a way to get it back, and separating them let a `content_filter` ending drop a block and hand over nothing — the client lost a passage it could not ask for again, on a line that read `[ OK ]`.
    #
    # `max_tokens` alone by default. `content_filter` is the obvious candidate for the list and is deliberately not on it: `refusal` is ruled uncontinuable, a filtered turn is its neighbour, and carrying one on would most likely be filtered again. It has also never been observed — zero occurrences across 134,336 recorded operations — so this is a door left open, not a case anyone has met.
    hand_over_stop_reasons: list[str] = Field(default_factory=lambda: ["max_tokens"])
    # The tool a turn that cannot be finished is handed back as. The default is what Claude Code calls the one this project ships beside it — `mcp__plugin_<plugin>_<server>__<tool>` is that client's naming for a plugin-provided MCP server, so the same server configured directly, or a renamed plugin, is a different name and this is how it gets said.
    auto_retry_tool_call_full_name: str = (
        "mcp__plugin_ghc-api-proxy-helper_auto-retry__turn_interrupted"
    )


class ProactiveRateLimiterConfig(Section):
    """The bound that replaced byte-level memory accounting.

    Ruled 2026-08-19. 50 is a ceiling for a pathological client, not a throttle: real traffic is
    429 requests across a whole day. A request over the limit waits rather than being refused — see `app.server.admission` for why refusing is worse than waiting.
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

    # Where the system prompt goes. `instructions-joint-string` puts the blocks in the top-level `instructions` as one `\n\n`-joined string, which is the only form this upstream accepts today. Kept as a named setting rather than baked in so a second placement — `as-role-system`, a `role: system` message at the head of the conversation — can be added without the caller changing.
    system_prompts: SystemPromptPlacement = "instructions-joint-string"

    # Whether this leg offers hosted web search at all. **Off by default**, ruled 2026-08-21: the support is real but partial, and the parts that remain missing are not visible to the client.
    # A search runs upstream and the response is restored as `server_tool_use` / `web_search_tool_result`, but Responses supplies no genuine Anthropic `encrypted_content`, so the structured result is reported as unavailable while the model's answer remains text. `max_uses` cannot be sent; `allowed_domains` / `blocked_domains` cannot be sent either and are dropped by the current default.
    # Shipping that on by default would still make a partial feature the thing every request gets.
    #
    # Off does **not** mean the declaration is quietly removed. The request is answered with a failed `web_search_tool_result`, the same as for a model no pattern claims — because on this client a search is its own sub-request carrying nothing but the search, and one stripped of it answers from memory under a heading the client reads as search results. The two are distinguished in the log, which is where an operator has to be able to tell "nobody turned this on" from "this model is not on the list".
    #
    # `models_support_web_search` is the other axis and still applies when this is on: this says whether the feature is offered, that says which models can run it.
    hosted_web_search: bool = False

    # `allowed_domains` / `blocked_domains` cannot reach this upstream — measured `Unknown parameter` for each — and they are a *narrowing* the client asked for, whose loss cannot be detected afterwards: the search runs upstream and its results reach the model directly, so this proxy never sees which sites were read.
    #
    # `drop_fields` sends the search without them. The results may come from outside the requested set, and the widening is recorded but cannot be checked.
    # `error` refuses the request before calling upstream, naming the field.
    #
    # There is deliberately no setting that removes the declaration and lets the turn continue.
    # On this client a web search is its own sub-request carrying nothing but the search, so a request stripped of it does not fail — the model answers from memory and the client labels the reply as search results. Refusing is the only honest way to not search.
    #
    # The default is `drop_fields`, which is *not* what the spec's D1 ruling wrote down. That ruling chose `error`, reading a domain list as a restriction the user had deliberately added for that search. Measured 2026-08-20 over 190 real Claude Code sub-requests, every single one carries a non-empty `allowed_domains` — the client sends it unconditionally, as part of how its WebSearch tool is built. Under `error` that makes web search permanently unavailable rather than occasionally refused, which is not the trade the ruling was making. Set `error` to have it back.
    web_search_domain_restrictions: WebSearchConstraintPolicy = "drop_fields"


class ModelTranslationConfig(Section):
    to_openai_responses: ToOpenAiResponsesConfig = Field(
        default_factory=ToOpenAiResponsesConfig
    )


class ClientDeliveryConfig(Section):
    # Measured from admission and never reset by retries, so it bounds the whole operation.
    #
    # **Not** the base for the systemd stop timeout, which this comment claimed until 2026-08-27. That number is `SYSTEMD_STOP_TIMEOUT_SECONDS` in `contrib/systemd/install-user.py`, which is `DEFAULT_GRACEFUL_TIMEOUT_SECONDS + 30` — 330s against this key's default of 3600. Nothing anywhere derives one from the other, and an operator who raised this expecting the unit file to follow would have changed neither.
    client_request_deadline: int = Field(default=3600, ge=0)
    buffering_policy: BufferingPolicy = "block"
    buffer_cap_bytes: int = Field(default=16_777_216, ge=0)
    sse_ping_interval: int = Field(default=15, ge=0)
    # What to put on the wire when upstream closed cleanly at a block boundary without ever sending its terminal event. There is no true answer to report — upstream never said why it stopped — so this names the synthesis rather than hiding it.
    #
    # Default `incomplete`, which is upstream's own word for a reply that stopped without finishing and is already what the Responses assembler records when upstream says `response.incomplete` with no reason. Claude Code's schema for this field is a nullable string with no enumeration and its readers compare against known values and skip the rest, so a word it does not know costs it nothing.
    #
    # `end_turn` is available and is what this used to fall back to, but it claims a turn upstream never claimed.
    #
    # **Empty turns the whole refinement off**: a clean EOF with no terminal event goes back to being reported as a failure, which is what this did before 2026-08-22 and what an operator who would rather see a loud truncation than a quiet one should set. It is an off-switch rather than a third wire shape because the alternative — closing the message with no `message_delta` at all — needs a framing path neither format has, and buying one for a case nobody has asked for is the wrong trade.
    #
    # **What that failure looks like on the wire stopped being only an SSE error on 2026-08-24.** Since then a reported failure with a whole block already delivered is offered to the hand-over first, so on the production shape — an Anthropic Messages client with the continuation tool configured — emptying this yields a `turn_interrupted` tool call rather than `incomplete_responses_stream`. The SSE error is what remains when the hand-over does not apply. Loud either way, which is what an operator setting this is asking for; but it is not the same frame, and this comment used to promise the frame.
    #
    # Only reached at a block boundary. A stream cut *through* a block is a truncation whatever this says, and still ends in a reported failure — which, by the same 2026-08-24 change, is a hand-over where one applies.
    unterminated_stream_stop_reason: str = "incomplete"
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
    # Keyed by model, valued by the `anthropic-beta` flags that model must not be asked for. A capability beta is not a global switch: upstream answers `400 invalid beta flag` when a model is asked for one it does not have, so the whole request dies over a header the client sent to every model alike. Per-model because that is the granularity of the rejection.
    # A key is a **regular expression** matched with `fullmatch` against the resolved model, and the first entry that matches wins.
    strip_anthropic_beta_flags: dict[str, list[str]] = Field(
        default_factory=lambda: dict[str, list[str]]()
    )
    # Whether to remove the attribution line Claude Code puts at the top of `system[0]`. Off by default, which is the ruling in `message-format-reshape.md` as of its 2026-08-22 revision — an earlier revision called the same strip resident, and it was briefly implemented that way.
    # Off is the safe default for a reason this project measured rather than assumed: upstream accepts the line in all fifteen shapes tried, so nothing breaks by leaving it, while the strip itself has a false-positive surface — a line has to be recognised as attribution, and prose that opens `Read-only: …` is not far from one that opens `x-something: …`. What it buys is 34 tokens per request on upstream's own counter, which is worth having and not worth defaulting to.
    strip_attribution_header: bool = False


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
    # Default `passthrough`, ruled 2026-08-24. `display` is a legal field on the adaptive shape rather than something this proxy has to repair, and the value Claude Code sends — `omitted` — is already the upstream default for the Claude 5 family, so forwarding it neither adds risk nor changes what the client said. The switch exists because `summarized` has a real use: it is what makes upstream return readable reasoning instead of `thinking` blocks whose text is empty.
    display: ThinkingDisplayPolicy = "passthrough"
    strip_all_thinking_blocks_on_reject: StripAllThinkingOnRejectConfig = Field(
        default_factory=StripAllThinkingOnRejectConfig
    )


class InterceptAutoModeClassifierConfig(Section):
    """Answer Claude Code's auto mode authorisation requests here instead of forwarding them.

    With auto mode on, that client asks a model to approve each action before running it, as its own non-streaming request carrying the rendered transcript, the user's whole `CLAUDE.md`, and a 110k-character monitor prompt. One measured sample is 710179 bytes, and one is spent per tool call. `app.pipeline.auto_mode_classifier` recognises them; this section says how to recognise them and what to answer.

    **Why it lives under this hook.** This section is the `on_client_request_parsed` moment and its scope is the Anthropic Messages leg — exactly the scope of this interception: the markers read `system` and `messages`, and the reply is an Anthropic Message. The short circuit fires immediately after `fix_anthropic_request()` returns, before translation.

    **What is different from its siblings.** Everything else in this hook reshapes a body that is then sent; this one answers instead of sending, so `fix_anthropic_request()` does not read it — `handle()` does. The section says when and to what this applies, not which function implements it.
    """

    # What to answer. `passthrough` — the default — forwards the request upstream like any other, so the feature is inert until somebody turns it on.
    #
    # `allow` and `block` answer locally with a fixed decision. **They do not judge anything**: the proxy cannot read the action under review and does not try, so this is a switch, not a cheaper classifier. Turning it on replaces auto mode's review with a constant, and the client still presents each answer as a model's — it renders an allow as `Allowed by fast classifier` and counts it in auto mode's telemetry.
    #
    decision: AutoModeDecision = "passthrough"

    # What the `<reason>` block says on a block. Not a recognition setting — this one is *output*, and it is the only part of this feature the person being blocked ever sees: Claude Code renders it as the explanation for why the action was refused.
    #
    # Written on a block only. The classifier prompt asks for no `<reason>` when the action is allowed, and an allow needs no explanation to a client that is about to proceed anyway.
    #
    # **It must not contain a `<block>` tag in any casing.** The client scans the whole reply with `/<block>(yes|no)\\b/gi` before reading anything, and returns "unparseable" the moment it sees two different decisions — so a reason quoting `<BLOCK>no</BLOCK>` under `decision: block` would make the reply unreadable, and unreadable costs a **retry** of the original 710 KB rather than one wrong answer. The implementation checks for it and drops the whole reason instead: better an unexplained block than a broken reply.
    block_reason_str: str = "Blocked by proxy, without a model review."

    # One of two **independent** recognition markers; either matching is enough, though both still sit behind the structural floor in `app.pipeline.auto_mode_classifier`. The other marker — the `<transcript>` wrapper the client puts around the rendered conversation — is a module constant there rather than a setting.
    #
    # **Why this one is configurable and that one is not.** They are both string literals owned by another program, but they are not equally likely to change: this is a sentence of English prose and gets reworded, while the wrapper is a structural tag. That asymmetry is the whole argument.
    #
    # A second reason was offered when the wrapper was pinned — its value must carry the trailing newline exactly, so it is easy to set wrongly and fails silently — and review showed it does **not** discriminate: setting *this* key wrongly fails just as silently. It is recorded as the minor point it is rather than dropped, so the next reader does not re-derive it as decisive.
    #
    # This is the opening line of the classifier's own system prompt, copied verbatim. A request matches when **any** of its system blocks starts with it — any block rather than `system[0]`, because the client puts its billing attribution in a system block too and which one comes first has already differed between recorded traffic and the current client source.
    match_system_prompt_prefix: str = "You are a security monitor for autonomous AI coding agents."



class FixAnthropicRequestHook(Section):
    # `sanitize` by default, ruled 2026-08-24. The mode's *meaning* was ruled separately and earlier — `passthrough` forwards the client's markers literally, refused keys included — and both rulings stand: this one only decides which mode applies when nobody wrote one down.
    #
    # Defaulting to a mode that edits the body is only defensible because of what `sanitize` became in the same ruling: it removes the fields `cache_control_sanitize` names for the answering model and nothing else, so the default's reach is a table an operator can read, narrow, or empty — not a blanket rewrite.
    cache_control: CacheControlMode = "sanitize"

    # Keyed by model, valued by the `cache_control` subfields that model refuses. A key is a **regular expression** matched with `fullmatch` against the resolved model, first entry wins — the same shape and the same caveats as `strip_anthropic_beta_flags`, including that `.` is a wildcard.
    #
    # **Deliberately a denylist rather than an allowlist**, ruled 2026-08-24. An allowlist would also catch the next field Anthropic invents, since upstream's schema is strict and refuses anything it does not know; the cost is that it strips fields upstream does accept, now or later, and cannot express "this model refuses it but that one does not". The ruling took the other side: name what is known to fail, leave everything else alone, and pay for a genuinely new field with one line of config rather than a release. `.dev/docs/anthropic-direct-request-shape/spec.md` §7.2 carries the full accounting.
    #
    # Empty here on purpose. The shipped table lives in `bundled-config.yaml`, which is where operational knowledge belongs — repeating it as a schema default would put the same fact in two places to drift apart.
    cache_control_sanitize: dict[str, list[str]] = Field(
        default_factory=lambda: dict[str, list[str]]()
    )
    extended_cache_ttl: ExtendedCacheTtlConfig = Field(default_factory=ExtendedCacheTtlConfig)
    context_editing: ContextEditingConfig = Field(default_factory=ContextEditingConfig)
    thinking: RequestThinkingConfig = Field(default_factory=RequestThinkingConfig)
    intercept_auto_mode_classifier: InterceptAutoModeClassifierConfig = Field(
        default_factory=InterceptAutoModeClassifierConfig
    )


class SseThinkingConfig(Section):
    content_block_start_compat: ContentBlockStartCompat = "signature_delta"


class RewriteRefusalConfig(Section):
    action: RefusalAction = "as_end_turn"
    text: str = "Please rephrase your request with a more safe statement."


class FixAnthropicSseHook(Section):
    thinking: SseThinkingConfig = Field(default_factory=SseThinkingConfig)
    fix_malformed_unicode_escape: bool = True
    rewrite_refusal: RewriteRefusalConfig = Field(default_factory=RewriteRefusalConfig)


class FixResponsesRequestHook(Section):
    # **Off by default, and it stays off**: `.dev/docs/direct-passthrough/spec.md` §2.7 requires a compatibility reshape on a native leg to be declared and optional, never folded into what is called verbatim. The user ruled the switch and its narrow shape together on 2026-09-01.
    #
    # What it turns on: an inbound `reasoning` item that carries `encrypted_content` **and** whose `id` matches the one shape `ResponsesFramer._item_id` could emit has that `id` removed before the body goes upstream. Upstream verifies the seal against the id it issued, so such a pair is refused every time it is replayed — permanently, for any client that keeps a rollout history. GitHub issue #4.
    #
    # It repairs history rather than behaviour: nothing produces that pair any more, since `1fb37cd` carries upstream's own events. Leave it off unless a conversation from before that commit is worth keeping alive. `app.pipeline.subscribers.minted_reasoning_ids` holds the predicate and why each part of it is needed.
    repair_minted_reasoning_ids: bool = False


class FixResponsesSseHook(Section):
    # **The name is the user's own**, written into `docs/.human-controlled/config.example.yaml` before any of this existed: "修复上游流在 `output_item.added` / `output_item.done` 间不一致的 item ID。`@ai-sdk/openai` 校验 ID 连续性需要。" The measurement is wider than that sentence — every id in the stream drifts, not only the two it names — but the key keeps their spelling.
    #
    # **On by default**, per the user's 2026-09-04 ruling after Claude Code failed with the known `activeReasoningPart.summaryParts` symptom while this reshape was disabled. This remains a named compatibility transform rather than part of native passthrough: an operator can set it to `false` to preserve every upstream id byte-for-byte. `.dev/docs/direct-passthrough/spec.md` §6.6.
    #
    # Who it is for is the client the user named: one that checks an item's id is the same on `added` and `done`. Nothing inside this proxy needs it — the engine keys on `output_index`. The earlier Codex rationale remains falsified; this default rests on the independently observed Claude Code failure, not on Codex.
    fix_stream_ids: bool = True


def _reject_unaddressable_provider_names(value: object) -> None:
    """Refuse a `model_providers` key that the qualifier syntax cannot name.

    Two shapes, both of which the schema accepted until 2026-08-27 and neither of which can be routed to:

    - **Containing `/`**: qualifiers split on the *first* separator, so a provider called `A/B` referenced as `A/B/model` is read as the unknown provider `A` and sent to the fallback. The configuration is accepted, the service starts, and the provider is reachable only as the default — every mapping value and request prefix naming it silently means something else.
    - **Empty or blank**: `/model` has an empty head, which the spec defines as an *unrecognised* provider precisely so a dropped provider name takes the fallback path. Configure a provider named `""` and that definition inverts — the typo becomes a hit.

    Raised at the configuration boundary rather than repaired at request time: both are static properties of the name, and a deployment that has to discover them from a routing error has already been serving traffic to the wrong place.

    The `/` here is the same character as `app.pipeline.model_resolution.QUALIFIER_SEPARATOR`, written literally rather than imported to keep the config schema from depending on the pipeline. `test_the_qualifier_separator_matches_the_config_boundary` is what keeps the two from drifting.
    """
    if not isinstance(value, dict):
        return
    for name in cast(dict[object, object], value):
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                "model_providers: a provider name may not be empty or blank. The empty name "
                "cannot be written in a `provider/model` qualifier, and `/model` is defined to "
                "mean an *unrecognised* provider so that a dropped name takes the fallback path."
            )
        if "/" in name:
            raise ValueError(
                f"model_providers: provider name {name!r} contains '/', which is reserved as the "
                "separator in `provider/model` qualifiers. A provider named this way cannot be "
                "addressed by any mapping value or request prefix — the part before the first "
                "'/' would be read as the provider name."
            )


class ProxyConfig(Section):
    server: ServerConfig = Field(default_factory=ServerConfig)
    inbound: InboundConfig = Field(default_factory=InboundConfig)

    # The sole source of model-name mapping; the spec forbids built-in defaults.
    model_mappings: dict[str, str] = Field(default_factory=lambda: dict[str, str]())

    # Which `output_config.effort` to ask an Anthropic Messages upstream for, per model.
    #
    # **Keyed on the resolved model id — the name upstream actually receives — not on the name the client asked for and not on a `model_mappings` key.** An effort is a capability of the model that answers, so an alias is looked through, exactly as `strip_denied_beta_flags` looks through one. That sibling is why this is stated here rather than left implied: its table in `config.example.yaml` is keyed `claude-sonnet-4.6`, which is a `model_mappings` *key* in the same file, so with both sections in force the whole table matches nothing. The request shape that produced this feature is the same one — `claude-sonnet-4-5` mapping to `claude-sonnet-5`.
    #
    # Empty by default, and an absent entry means **send no `output_config` at all**, which upstream reads as its own default of `high`. There is deliberately no fallback value: a default here would put every request on a cost dial nobody set. Whatever is configured is aligned against the effort names the catalog publishes for that model before it is sent — see `app.pipeline.subscribers.anthropic_thinking`.
    model_thinking_effort: dict[str, str] = Field(default_factory=lambda: dict[str, str]())

    model_translation: ModelTranslationConfig = Field(default_factory=ModelTranslationConfig)

    model_providers: dict[str, ModelProviderConfig] = Field(
        default_factory=lambda: dict[str, ModelProviderConfig]()
    )
    default_model_provider: str = ""

    # Where a request goes when its mapping value **named** a provider that is not configured — `x: typo/claude-opus-5`. Deliberately a second key rather than a reuse of the one above, because "the operator wrote no qualifier" and "the operator wrote one and got it wrong" are different facts and only the second is a defect. Folding them together would make a typo indistinguishable from the ordinary case, which is precisely the state this key exists to end.
    #
    # May be left unset, and then such a request is **refused** rather than quietly served by the default. Refusing is the fail-closed direction: the alternative sends a request to an upstream nobody named, and the operator's evidence that anything was wrong is a bill on the wrong account.
    #
    # Naming a provider that does not exist stops start-up, exactly as `default_model_provider` does. Spec §1.2.
    fallback_model_provider: str = ""

    @field_validator("model_providers", mode="before")
    @classmethod
    def _names_must_be_addressable(cls, value: object) -> object:
        _reject_unaddressable_provider_names(value)
        return value

    @model_validator(mode="after")
    def _counter_legs_name_something_that_exists(self) -> ProxyConfig:
        """Check `inbound.anthropic_count_tokens.providers` against the providers this config declares.

        Here rather than on `CountTokensConfig` because this is the first place both halves are in scope, and **relative to the configuration rather than to a fixed list** because that is what the field always meant: `ghc` is valid in a deployment that configures a provider called `ghc`, and means nothing in one that does not. A `Literal` in its place answered the question without looking.

        Two things are deliberately not checked.

        **A config with no providers at all.** That is not a bad counting leg, it is a `ProxyConfig` built without the section that supplies providers — the bundled defaults carry one, and a config lacking them fails at `resolve_default_name` with a message about the thing that is actually missing. Reporting the counting leg there would name a consequence and hide the cause.

        **The default value.** `["ghc", "local"]` names the provider the bundled config ships, and a deployment that renames its providers without touching this key has done nothing wrong: the upstream leg asks whichever provider routing chose, so the string only has to be "not local" for the default to behave correctly. What an operator **writes** is a declaration and is checked; what they inherited is not.
        """
        counting = self.inbound.anthropic_count_tokens
        if not self.model_providers or "providers" not in counting.model_fields_set:
            return self
        for leg in counting.providers:
            if leg != LOCAL_COUNTER and leg not in self.model_providers:
                configured = ", ".join(sorted(self.model_providers)) or "none"
                raise ValueError(
                    f"inbound.anthropic_count_tokens.providers: {leg!r} is neither "
                    f"{LOCAL_COUNTER!r} nor one of this deployment's model providers "
                    f"(configured: {configured})"
                )
        return self

    # A directory, not a file: the name inside it carries the port, so one setting covers every instance an operator runs rather than having to be re-stated per port.
    pidfile_dir: str = ""
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
    hook_fix_responses_request: FixResponsesRequestHook = Field(
        default_factory=FixResponsesRequestHook
    )
    hook_fix_responses_sse: FixResponsesSseHook = Field(default_factory=FixResponsesSseHook)

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
