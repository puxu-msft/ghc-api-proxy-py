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
        "model_providers.*.auth_base_url",
        "model_providers.*.github_token_file",
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
    # A separate host from the one above, and separately configurable: an enterprise install moves both, and leaving this one a module constant meant nothing could be stood up locally — the inference calls could be redirected and the three auth calls could not.
    auth_base_url: str = ""
    # May contain `$XDG_DATA_HOME`; expanded by `app.config.paths.expand_user_path`.
    github_token_file: str = ""
    model_refresh_interval: int = Field(default=3600, ge=0)
    disabled_models: list[str] = Field(default_factory=lambda: list[str]())
    # Which models actually execute hosted web search. Each entry is a **regular expression**, matched against upstream `model.id` with `fullmatch` — so a plain id like `gpt-5.5` still means what it says and needs no anchors, while `gpt-5\.\d+.*` covers a family. A declaration from the client is translated into this endpoint's own `{"type": "web_search"}` only for a model some pattern claims. For any other, the request is answered with a failed `web_search_tool_result` rather than sent on without the tool: a search sub-request stripped of its only tool succeeds by answering from memory, and the client labels that reply as search results.
    #
    # Maintained by hand because the catalog cannot answer the question. Measured 2026-08-20 across the live catalog — 42 models, 67,656 bytes — the union of `capabilities.supports` keys holds no web-search bit of any kind, and a value-level scan for `search|web_|builtin|hosted` over the whole document returns nothing. The two models known to work cannot be told apart from the rest on any advertised field.
    #
    # The default covers the `gpt-<major>.<minor>` line for majors 5 through 9, which is every
    # OpenAI-vendor model advertising `/responses` in that catalog — `gpt-5.3-codex`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.5`, and the three `gpt-5.6-*` — and claims their successors as they appear. Ruled a pattern rather than an id list on 2026-08-21, after an id list had to be hand-extended for exactly that reason.
    #
    # **The dot is load-bearing.** `gpt-5-mini` has no dotted minor and is vendor `Azure OpenAI`, a different supply chain; requiring `\.` is what keeps a family pattern from sweeping it in. A two-digit major (`gpt-10.0`) is deliberately not matched: inventing a naming scheme two majors ahead is a guess, and the failure is an operator adding one line, not a wrong answer.
    #
    # Both ways of being wrong show up, and neither is silent. A model claimed here that cannot search answers 400 and says which value it refused. A model no pattern claims has its search answered as failed, which is reported at INFO with the model named.
    models_support_web_search: list[str] = Field(
        default_factory=lambda: [r"gpt-[5-9]\.\d+.*"]
    )


class UpstreamTransportConfig(Section):
    # A real TCP keep-alive: seconds of idle before the first probe, and seconds between probes. 0 disables it. Until 2026-08-20 this key was mapped to httpx's connection-pool idle expiry instead, which never writes a byte to the socket and does not apply at all while a request is in flight — so the name promised liveness the transport never had. Nothing replaces that mapping: pooling is httpx's own business and was never a setting anyone chose.
    # What it can tell you depends on whether a proxy is in the way. TCP keep-alive is per-connection, and a proxy terminates the connection: measured 2026-08-20, our socket's peer is the origin when direct and the proxy when tunnelling through one. So with a proxy configured this probes the hop to the proxy and says nothing about upstream, whose connection is the proxy's to keep.
    tcp_keepalive_interval: int = Field(default=15, ge=0)
    # Set false to negotiate HTTP/1.1 upstream. Ruled 2026-08-20, after one upstream GOAWAY killed every in-flight stream at once: HTTP/2 multiplexes them onto one connection, so one connection-level event is one blast radius. HTTP/1.1 gives each request its own connection and costs more handshakes. See `.dev/docs/upstream/h2-goaway/findings.md`.
    # Authoritative on its own. It used to be derived from `http2_ping_interval > 0`, which meant a key named after a ping interval silently decided the protocol.
    http2: bool = True
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

    # Whether this leg offers hosted web search at all. **Off by default**, ruled 2026-08-21: the support is real but partial, and the parts that are missing are not visible to the client.
    # A search runs upstream and really searches, but what comes back to an Anthropic client is a line of text rather than the `server_tool_use` / `web_search_tool_result` pair the protocol defines; `url_citation` annotations upstream does return are not read; `max_uses` cannot be sent; `allowed_domains` / `blocked_domains` cannot be sent either and are dropped by default.
    # Shipping that on by default would make a half-built feature the thing every request gets.
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
    # Also the base for the systemd stop timeout.
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
    cache_control: CacheControlMode = "passthrough"
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

    model_config = ConfigDict(frozen=True, extra="forbid")
