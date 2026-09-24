# Command Code provider

## Status

Living implementation Spec for the `type: commandcode` provider. The provider is
an upstream wire target, not an OpenAI-compatible endpoint.

## Contract

1. Command Code inference is sent to `POST /alpha/generate`.
2. Command Code model discovery is sent to `GET /provider/v1/models`.
3. The upstream request body is the Command Code envelope:
   `config`, `memory`, `taste`, `skills`, `permissionMode`, and `params`.
4. `params.stream` is always `true` on the upstream leg. A non-streaming client
   is served by buffering and aggregating the upstream NDJSON event stream.
5. The internal route target is a distinct `commandcode` wire format and a
   distinct `/alpha/generate` model endpoint. It must not be represented as
   `openai-chat-completions` or `openai-responses`.
6. The provider translates through the semantic IR. The request codec and the
   response/event codec are the only places that know Command Code field names.
7. The provider supports text, visible reasoning, image data URLs, function tools,
   tool results, tool choice, usage, upstream errors, streaming and buffered
   replies. Unsupported semantic blocks or fields are recorded as conversion
   losses or refused when removal would change the request's meaning.
8. Client-facing streaming is still block-level. Complete Command Code events are
   assembled into internal blocks before the selected client framer writes them.
9. `previous_response_id` and `store` are not Command Code capabilities. They must
   not be forwarded or silently emulated.
10. Token counting has no Command Code upstream endpoint and therefore uses the
    existing local estimator path.
11. Authentication and lifecycle headers are provider-owned. Client headers may
    not replace `Authorization`, `x-command-code-version`, `x-session-id`,
    `x-project-slug`, or other provider-owned headers.
12. Fingerprint/lifecycle initialization is per API key, best-effort, and must
    never prevent the inference request from being attempted when initialization
    itself fails. Lifecycle initialization remains enabled by default.
    Fingerprint handling is separately configurable and defaults to `off`.
    `captured` and `explicit` modes read a validated local snapshot; `generated`
    mode creates an opaque proxy-owned value. `off` sends no fingerprint.
    Captured or explicit snapshots must be bound to the configured API key and
    have a future expiry; an unavailable or invalid snapshot is reported and
    does not fall back to generation.
13. Tool results are emitted as Command Code `role: "tool"` messages, one
    message per result, preserving result order. When ordinary content shares
    the user turn, all tool-result messages precede the ordinary user message
    because Command Code requires that order. The result block retains its
    `toolCallId` and resolved `toolName`.
14. Buffered client responses use the installed client dialect schema. Responses
    bodies carry the complete response envelope, valid output-item fields, and
    the full Responses usage object; Chat Completions bodies carry
    `created`/`id`/`model`/`choices` and Chat usage fields. These are the same
    conventions used by the existing Responses framer and response writers.
15. A clean upstream EOF does not turn an unfinished text, reasoning, or tool
    draft into a completed block. `cut_mid_block` remains true so generic
    delivery can retry, hand over, or report the truncation. A terminal with no
    output is an upstream zero-output failure, never a successful empty HTTP
    200 body. If a synthesized stop reason has no legal spelling on the client
    dialect, delivery emits that dialect's error shape instead of exposing the
    internal `incomplete` value. A completed terminal must carry an explicit
    usage `outputTokens` value: missing usage is distinct from an explicit
    `outputTokens: 0`, and neither may become an unobserved successful 200.
16. Chat `reasoning_effort` is preserved. Anthropic enabled-thinking budgets
    map to Command Code effort at 2000 → `low`, 5000 → `medium`, and 10000 →
    `high` thresholds; Anthropic adaptive thinking maps explicitly to `medium`;
    an absent Anthropic effort does not silently become `high`.
17. When no interaction header is supplied, Command Code uses the provider's
    stable fallback session. A client `prompt_cache_key` may supply the fallback
    session identity where the request translation retains it; an explicit
    interaction header always wins.
18. Responses input accepts both the scalar string form and easy message items
    whose `type` is omitted. `system` and `developer` input items become the
    Command Code system string. Responses `message`, `reasoning`, and
    `function_call` items that make one assistant turn are merged before
    rendering. `parallel_tool_calls` is independent of `tool_choice` and is
    forwarded when explicitly present.
19. Command Code tool declarations carry only function tools. Responses
    builtins, custom tools, MCP tools, and tool-search tools are not rewritten
    as empty functions; they are omitted with a conversion loss. Responses
    function tools are rendered only when their type is explicitly `function`.
20. A Responses `input_image` with a string `image_url` becomes Command Code
    image data, including data URLs and source URLs. File-backed image forms
    such as `file_id` have no Command Code representation and are recorded as
    conversion losses rather than silently dropped.
21. Command Code `params.max_tokens` defaults to 64000 only when the semantic
    request has no explicit output-token limit. An explicit limit must be
    positive; zero and negative values are refused rather than replaced by the
    default. Positive values are capped at 200000. Buffered aggregation
    preserves safe transport extensions, including `http_version` and
    connection diagnostics, together with the canonical
    `upstream_raw_response_body`; it never carries the consumed transport
    stream into the rebuilt response.
22. Function tools use an empty object schema when `parameters` or
    `input_schema` is null or absent. A null description is treated as absent,
    never rendered as the string `"None"`. Function-tool fields with no
    Command Code spelling, including `strict`, `allowed_callers`,
    `output_schema`, and `defer_loading`, are recorded as conversion losses.
    Non-function Responses tools remain omitted with a conversion loss.
23. Command Code usage reads both camelCase and snake_case input-token detail
    names. `cacheReadTokens` / `cache_read_tokens` provide the cache-read
    count when present; `noCacheTokens` / `no_cache_tokens` remains authoritative
    for fresh input. Anthropic, Responses, and Chat projections are derived from
    that same normalized accounting.
24. A translated request may carry request-scoped `x-cmd-zdr: 1`. It is
    extracted only for the Command Code target after the general translated
    header policy, and is never added to the translated-path header allowlist.
    Session identity remains request-scoped through the extracted interaction
    id or the request's `prompt_cache_key` fallback. Provider-owned project and
    Command Code version headers remain provider-configured; this project
    intentionally does not discover a replacement version from an undocumented
    endpoint.
25. Responses reasoning with encrypted-only history cannot be represented by
    Command Code. The translation refuses it rather than silently deleting the
    history state. Visible summaries may cross, but the lost opaque state is
    recorded. Responses EasyInputMessage `phase` is retained in the semantic
    message IR; Command Code records a loss because it has no phase field.
26. Buffered Responses-to-Anthropic conversion records
    `opaque-response-skipped` only for an opaque output item. Unknown
    Responses top-level response metadata is not semantic output and does not
    create that loss. When a configured static model list exists, a failed
    Command Code catalog refresh keeps serving that static catalog.
27. The Command Code request writer asks the semantic request for both
    source-scoped top-level and nested extensions. Extensions with no Command
    Code spelling are recorded as explicit conversion losses. Fields already
    consumed by a Command Code mapping, including `prompt_cache_key` and the
    reasoning fields used to choose an effort, are excluded from that loss
    accounting and are not reported twice.
28. Responses `incomplete_details.reason` uses the installed SDK's legal
    enumeration: `max_output_tokens`, `max_messages`, `content_filter`, or
    `steered`; the corresponding semantic stop reasons are mapped to those
    spellings rather than emitted as an invalid value or silently nulled.
29. A Responses `function_call_output` must carry a non-empty string
    `call_id`. A missing or null identifier is refused before translation
    rather than becoming the literal string `"None"` or an uncorrelatable
    Command Code tool result.
30. When an upstream attempt fails after producing a response body, the
    original bytes are recorded through the same
    `RawRequestCapture.upstream_response_body` event used by successful and
    discarded responses. Completion-line rendering has a complete Command
    Code dialect mapping for reasoning, tools, and response-byte thresholds.
31. Responses execution, conversation-state, prompt-template, and
    structured-output controls that Command Code cannot preserve are refused
    before the upstream request, including `background`, `conversation`,
    `context_management`, `moderation`, `prompt`, `include`, `max_tool_calls`,
    `stream_options`, `text`, `top_logprobs`, `top_p`, and `truncation`.
    Advisory fields such as metadata, service tier, user/safety identifiers,
    and prompt-cache policy remain conversion losses when they do not affect
    the generated request semantics. `previous_response_id` and `store`
    retain their existing state refusal.
32. A forced tool choice is validated against the final Command Code function
    tools after unsupported Responses tools have been filtered. A choice for
    a missing or filtered function, custom tool, builtin, or MCP tool is
    refused; it is never emitted as a dangling choice or changed to `auto`.
33. A Responses request with non-empty `instructions` and no `input` is
    valid for Command Code. The empty-request refusal applies only when both
    the rendered system string and rendered message list are empty.
34. The eight-hour initialization window is set only after every enabled
    initialization request returns success. With a usable fingerprint snapshot
    or generated fingerprint this means both fingerprint and lifecycle requests;
    with fingerprint mode `off` or an unavailable captured/explicit snapshot
    only the lifecycle request is required. Any failure leaves initialization
    retryable on a subsequent request without blocking inference. Catalog
    requests use endpoint-specific headers and never carry `x-cmd-zdr`;
    generation, fingerprint, and lifecycle requests may carry it.

## Revision record

| Date | Change | Reason |
|---|---|---|
| 2026-09-13 | Created the living provider contract and fixed Command Code as an independent IR target. | User decision to implement the long-term IR-native design. |
| 2026-09-13 | Added dialect-schema, tool-role, zero-output, reasoning-effort, and session-fallback rules. | Command Code review fixes for the IR boundary and installed OpenAI SDK compatibility. |
| 2026-09-13 | Added Responses input-shape compatibility, explicit adaptive/parallel mappings, usage-presence semantics, and block-close/EOF rules. | Final Command Code review findings. |
| 2026-09-13 | Added explicit Responses tool/image conversion boundaries, the 200000 token cap, and safe buffered transport metadata rules. | Command Code release audit findings. |
| 2026-09-13 | Closed nullable tool fields, usage detail aliases, request-scoped ZDR, reasoning/phase losses, metadata loss accounting, and static catalog fallback. | Remaining Command Code release audit findings. |
| 2026-09-13 | Closed dialect completion logging, extension-loss accounting, current Responses incomplete reasons, failed-body capture, nullable function-result IDs, and explicit non-positive token limits. | Final release audit findings. |
| 2026-09-13 | Refused unrepresentable Responses controls and dangling forced choices, accepted instructions-only requests, made lifecycle success atomic with retry, and removed ZDR from catalog fetches. | Ultimate Command Code audit findings. |
| 2026-09-15 | Replaced the boolean fingerprint simulation switch with `off`/`captured`/`generated`/`explicit` source modes; captured and explicit snapshots are API-key-bound and expiry-checked, with no generated fallback. | User decision to prefer accurate information from a running Command Code CLI. |
