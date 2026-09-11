"""Anthropic Messages translators.

Reads and writes the typed content model rather than moving `dict`s around. `D-ARCH = B`: wire shapes live at this boundary and nowhere inside.
"""

from collections.abc import Mapping
from typing import Any, cast

from app.pipeline.translation_driver.content import BlockKind, ContentBlock, SemanticMessage
from app.pipeline.translation_driver.options import TranslationOptions
from app.pipeline.translation_driver.reasoning import (
    ANTHROPIC_EFFORTS,
    EFFORT_LADDER,
    EffortSource,
    ThinkingEffortIntent,
    align_anthropic_effort,
)
from app.pipeline.translation_driver.reasoning_bridge import (
    ReasoningBridgeError,
    ReasoningNotPortable,
    read_anthropic_reasoning,
    reasoning_to_anthropic,
)
from app.pipeline.translation_driver.semantic import (
    Conversion,
    ConversionFactCode,
    LossCode,
    SemanticRequest,
    SystemBlock,
    ToolChoiceNotSupported,
    TranslationRefused,
    TranslationTarget,
    system_blocks_from_value,
)
from app.pipeline.translation_driver.tool_choice import intent_from_anthropic_tool_choice

WIRE_FORMAT = "anthropic-messages"
CHAT_COMPLETIONS_WIRE_FORMAT = "openai-chat-completions"
RESPONSES_WIRE_FORMAT = "openai-responses"

_PASSTHROUGH_KEYS = frozenset(
    {
        "model",
        "system",
        "messages",
        "tools",
        "stream",
        "max_tokens",
        "temperature",
        "thinking",
        "output_config",
        "tool_choice",
    }
)

EFFORT_BETA = "mid-conversation-output-config-2026-07-01"
_CONTROL_MESSAGE_KEYS = frozenset({"role", "content", "output_config"})
_CONTROL_OUTPUT_KEYS = frozenset({"effort"})


def _reasoning_intent_refused(message: str, *, field_path: str) -> TranslationRefused:
    return TranslationRefused(
        message,
        code="reasoning-intent-invalid",
        field_path=field_path,
    )


def _thinking_enabled(
    payload: Mapping[str, Any],
    *,
    translated: bool,
    conversion: Conversion,
) -> tuple[bool, dict[str, Any] | None]:
    if "thinking" not in payload:
        return True, None
    thinking = payload["thinking"]
    if not isinstance(thinking, Mapping):
        raise _reasoning_intent_refused("thinking must be an object", field_path="thinking")
    field = dict[str, Any](cast(Mapping[str, Any], thinking))
    kind = field.pop("type", None)
    if not isinstance(kind, str):
        raise _reasoning_intent_refused(
            "thinking.type must be a string",
            field_path="thinking.type",
        )
    if kind not in {"disabled", "adaptive", "auto", "enabled"}:
        raise _reasoning_intent_refused(
            f"unknown thinking.type {kind!r}",
            field_path="thinking.type",
        )

    budget = field.get("budget_tokens")
    if "budget_tokens" in field:
        if isinstance(budget, bool) or not isinstance(budget, int):
            raise _reasoning_intent_refused(
                "thinking.budget_tokens must be an integer",
                field_path="thinking.budget_tokens",
            )
        if budget <= 0:
            raise _reasoning_intent_refused(
                "thinking.budget_tokens must be positive",
                field_path="thinking.budget_tokens",
            )

    if translated and kind == "auto":
        conversion.record(
            LossCode.REASONING_INTENT_APPROXIMATED,
            "thinking.type=auto accepted as a translated-path compatibility extension",
        )
    if translated and kind == "enabled" and budget is None:
        conversion.record(
            LossCode.REASONING_INTENT_APPROXIMATED,
            "thinking.budget_tokens absent on enabled thinking; accepted as a translated-path compatibility extension",
        )
    if translated and kind == "enabled" and isinstance(budget, int):
        max_tokens = payload.get("max_tokens")
        compatibility_reasons: list[str] = []
        if budget < 1024:
            compatibility_reasons.append("below the official 1024-token minimum")
        if (
            isinstance(max_tokens, int)
            and not isinstance(max_tokens, bool)
            and budget >= max_tokens
        ):
            compatibility_reasons.append("not below max_tokens")
        if compatibility_reasons:
            conversion.record(
                LossCode.REASONING_INTENT_APPROXIMATED,
                f"thinking.budget_tokens={budget} accepted as a translated-path compatibility extension: {', '.join(compatibility_reasons)}",
            )
    return kind != "disabled", field


def read_anthropic_thinking_effort(
    payload: Mapping[str, Any],
    *,
    translated: bool,
    conversion: Conversion,
) -> tuple[ThinkingEffortIntent, dict[str, dict[str, Any]]]:
    """Read Anthropic's independent thinking enablement and effort level without deriving either from a budget."""
    enabled, thinking_residual = _thinking_enabled(
        payload,
        translated=translated,
        conversion=conversion,
    )
    nested: dict[str, dict[str, Any]] = {}
    if thinking_residual is not None:
        nested["thinking"] = thinking_residual

    source = EffortSource.ANTHROPIC_DEFAULT
    effort = "high"
    if "output_config" in payload:
        output = payload["output_config"]
        if not isinstance(output, Mapping):
            raise TranslationRefused(
                "output_config must be an object",
                code="effort-invalid",
                field_path="output_config",
            )
        output_fields = dict[str, Any](cast(Mapping[str, Any], output))
        explicit_effort = output_fields.pop("effort", None)
        if "effort" in output:
            if not isinstance(explicit_effort, str) or explicit_effort not in ANTHROPIC_EFFORTS:
                raise TranslationRefused(
                    "invalid Anthropic effort",
                    code="effort-invalid",
                    field_path="output_config.effort",
                )
            effort = explicit_effort
            source = EffortSource.ANTHROPIC_TOP_LEVEL
        nested["output_config"] = output_fields

    return ThinkingEffortIntent(enabled=enabled, effort=effort, effort_source=source), nested


def _is_effort_control_candidate(raw: object) -> bool:
    return isinstance(raw, Mapping) and "output_config" in raw


def _anthropic_beta_tokens(headers: Mapping[str, str]) -> frozenset[str]:
    return frozenset(
        token.strip()
        for token in headers.get("anthropic-beta", "").split(",")
        if token.strip()
    )


def _parse_effort_control(
    raw: Mapping[str, Any],
    *,
    index: int,
    source_headers: Mapping[str, str],
) -> str:
    field = f"messages[{index}]"
    extra = raw.keys() - _CONTROL_MESSAGE_KEYS
    if extra:
        key = sorted(extra)[0]
        raise TranslationRefused(
            f"unsupported effort control field {key!r}",
            code="effort-control-invalid",
            field_path=f"{field}.{key}",
        )
    if raw.get("role") != "system":
        raise TranslationRefused(
            "effort control role must be system",
            code="effort-control-invalid",
            field_path=f"{field}.role",
        )
    content = raw.get("content")
    if content != "" and content != []:
        raise TranslationRefused(
            "effort control content must be empty",
            code="effort-control-invalid",
            field_path=f"{field}.content",
        )
    output = raw.get("output_config")
    if not isinstance(output, Mapping):
        raise TranslationRefused(
            "effort control output_config must be an object",
            code="effort-control-invalid",
            field_path=f"{field}.output_config",
        )
    output_fields = cast(Mapping[str, Any], output)
    output_extra = output_fields.keys() - _CONTROL_OUTPUT_KEYS
    if output_extra:
        key = sorted(output_extra)[0]
        raise TranslationRefused(
            f"unsupported effort control output field {key!r}",
            code="effort-control-invalid",
            field_path=f"{field}.output_config.{key}",
        )
    effort = output_fields.get("effort")
    if not isinstance(effort, str) or effort not in ANTHROPIC_EFFORTS:
        raise TranslationRefused(
            "invalid per-message effort",
            code="effort-invalid",
            field_path=f"{field}.output_config.effort",
        )
    if EFFORT_BETA not in _anthropic_beta_tokens(source_headers):
        raise TranslationRefused(
            "per-message effort requires its beta header",
            code="beta-required",
            field_path=f"{field}.output_config.effort",
        )
    return effort


def _effective_per_message_effort(
    messages: list[object],
    *,
    source_headers: Mapping[str, str],
    baseline: str,
    baseline_source: EffortSource,
) -> tuple[str, list[object], EffortSource]:
    active = baseline
    source = baseline_source
    pending: str | None = None
    filtered: list[object] = []
    for index, raw in enumerate(messages):
        if _is_effort_control_candidate(raw):
            pending = _parse_effort_control(
                cast(Mapping[str, Any], raw),
                index=index,
                source_headers=source_headers,
            )
            continue
        filtered.append(raw)
        if (
            isinstance(raw, Mapping)
            and cast(Mapping[str, Any], raw).get("role") == "user"
            and pending is not None
        ):
            active = pending
            source = EffortSource.ANTHROPIC_PER_MESSAGE
            pending = None
    return active, filtered, source


TEXT = "text"
THINKING = "thinking"
REDACTED_THINKING = "redacted_thinking"
TOOL_USE = "tool_use"
TOOL_RESULT = "tool_result"
SERVER_TOOL_USE = "server_tool_use"
WEB_SEARCH_TOOL_RESULT = "web_search_tool_result"
IMAGE = "image"


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries = cast(list[object], value)
    return [dict[str, Any](cast(Mapping[str, Any], e)) for e in entries if isinstance(e, Mapping)]


def _dict_value(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return dict[str, Any](cast(Mapping[str, Any], value))


def _block_from_anthropic(raw: dict[str, Any]) -> ContentBlock:
    kind = str(raw.get("type", ""))
    if kind == TEXT:
        return ContentBlock(BlockKind.TEXT, text=str(raw.get("text", "")), raw=raw)
    if kind in {THINKING, REDACTED_THINKING}:
        try:
            reasoning = read_anthropic_reasoning(raw)
        except ReasoningBridgeError as error:
            raise TranslationRefused(
                error.detail,
                code=error.code,
                field_path=f"messages.content.{kind}",
            ) from error
        return ContentBlock(BlockKind.REASONING, reasoning=reasoning, raw=raw)
    if kind == TOOL_USE:
        return ContentBlock(
            BlockKind.TOOL_USE,
            call_id=str(raw.get("id", "")),
            name=str(raw.get("name", "")),
            arguments=raw.get("input"),
            raw=raw,
        )
    if kind == TOOL_RESULT:
        return ContentBlock(
            BlockKind.TOOL_RESULT,
            call_id=str(raw.get("tool_use_id", "")),
            output=raw.get("content"),
            is_error=bool(raw.get("is_error", False)),
            raw=raw,
        )
    if kind == SERVER_TOOL_USE:
        return ContentBlock(
            BlockKind.SERVER_TOOL_USE,
            call_id=str(raw.get("id", "")),
            name=str(raw.get("name", "")),
            arguments=raw.get("input"),
            raw=raw,
        )
    if kind == WEB_SEARCH_TOOL_RESULT:
        return ContentBlock(
            BlockKind.WEB_SEARCH_TOOL_RESULT,
            call_id=str(raw.get("tool_use_id", "")),
            output=raw.get("content"),
            raw=raw,
        )
    if kind == IMAGE:
        return ContentBlock(BlockKind.IMAGE, raw=raw)
    return ContentBlock(BlockKind.UNKNOWN, raw=raw)


def _message_from_anthropic(raw: Mapping[str, Any]) -> SemanticMessage:
    role = str(raw.get("role", ""))
    content = raw.get("content")
    if isinstance(content, str):
        return SemanticMessage(role, (ContentBlock(BlockKind.TEXT, text=content),))
    return SemanticMessage(role, tuple(_block_from_anthropic(b) for b in _dict_list(content)))


def from_anthropic_messages(
    payload: Mapping[str, Any],
    *,
    options: TranslationOptions | None = None,
    source_headers: Mapping[str, str] | None = None,
    translated: bool = False,
) -> SemanticRequest:
    if options is not None:
        source_headers = options.source_headers
        translated = options.translated
    blocks, problem = system_blocks_from_value(payload.get("system"))
    conversion = Conversion()
    thinking_effort, nested_extensions = read_anthropic_thinking_effort(
        payload,
        translated=translated,
        conversion=conversion,
    )
    raw_messages = payload.get("messages")
    message_values = cast(list[object], raw_messages) if isinstance(raw_messages, list) else []
    active_effort, filtered_messages, effort_source = _effective_per_message_effort(
        message_values,
        source_headers=source_headers or {},
        baseline=cast(str, thinking_effort.effort),
        baseline_source=thinking_effort.effort_source,
    )
    thinking_effort = ThinkingEffortIntent(
        enabled=thinking_effort.enabled,
        effort=active_effort,
        effort_source=effort_source,
    )
    model = payload.get("model")
    request = SemanticRequest(
        model=model if isinstance(model, str) else "",
        system=blocks,
        messages=[
            _message_from_anthropic(cast(Mapping[str, Any], message))
            for message in filtered_messages
            if isinstance(message, Mapping)
        ],
        tools=_dict_list(payload.get("tools")),
        stream=bool(payload.get("stream", False)),
        thinking_effort=thinking_effort,
        source_format=WIRE_FORMAT,
        nested_extensions=nested_extensions,
        conversion=conversion,
    )
    if problem is not None:
        request.conversion.record(problem, "system")

    max_tokens = payload.get("max_tokens")
    if isinstance(max_tokens, int):
        request.max_output_tokens = max_tokens
    temperature = payload.get("temperature")
    if isinstance(temperature, int | float):
        request.temperature = float(temperature)

    # Read the client's intent once; unclaimed shapes stay in extensions for same-format replay.
    choice = payload.get("tool_choice")
    request.tool_choice = intent_from_anthropic_tool_choice(choice)

    # Anything not claimed above is carried rather than dropped.
    # An unmodelled field therefore survives the round trip back to the same format.
    request.extensions = {
        key: value for key, value in payload.items() if key not in _PASSTHROUGH_KEYS
    }
    if request.tool_choice is None and "tool_choice" in payload:
        request.extensions["tool_choice"] = choice
    return request


def _system_value(blocks: list[SystemBlock]) -> list[dict[str, Any]]:
    return [{"type": TEXT, "text": block.text, **dict(block.metadata)} for block in blocks]


def block_to_anthropic(block: ContentBlock, conversion: Conversion) -> dict[str, Any] | None:
    """Render one response block for an Anthropic client."""
    return _block_to_anthropic(block, conversion, bridge_for_client=True)


def block_from_anthropic(raw: dict[str, Any]) -> ContentBlock:
    """Read one Anthropic content block into the typed model."""
    return _block_from_anthropic(raw)


def _block_to_anthropic(
    block: ContentBlock,
    conversion: Conversion,
    *,
    bridge_for_client: bool,
) -> dict[str, Any] | None:
    if block.kind is BlockKind.TEXT:
        return {"type": TEXT, "text": block.text}
    if block.kind is BlockKind.REASONING:
        return _reasoning_to_anthropic(
            block,
            conversion,
            bridge_for_client=bridge_for_client,
        )
    if block.kind is BlockKind.TOOL_USE:
        return {
            "type": TOOL_USE,
            "id": block.call_id,
            "name": block.name,
            "input": block.arguments if block.arguments is not None else {},
        }
    if block.kind is BlockKind.TOOL_RESULT:
        result: dict[str, Any] = {"type": TOOL_RESULT, "tool_use_id": block.call_id}
        if block.output is not None:
            result["content"] = block.output
        if block.is_error:
            result["is_error"] = True
        return result
    if block.kind is BlockKind.SERVER_TOOL_USE:
        if block.raw.get("type") == SERVER_TOOL_USE:
            return dict(block.raw)
        return {
            "type": SERVER_TOOL_USE,
            "id": block.call_id,
            "name": block.name,
            "input": _dict_value(block.arguments),
        }
    if block.kind is BlockKind.WEB_SEARCH_TOOL_RESULT:
        if block.raw.get("type") == WEB_SEARCH_TOOL_RESULT:
            return dict(block.raw)
        if block.output is None:
            conversion.record(
                LossCode.BLOCK_NOT_CARRIED,
                "web_search_tool_result has no content",
            )
            return None
        return {
            "type": WEB_SEARCH_TOOL_RESULT,
            "tool_use_id": block.call_id,
            "content": block.output,
        }
    # Image and unknown blocks have no modelled fields; their original is the only faithful rendering, and returning it is what keeps a same-format crossing exact.
    if block.raw:
        return dict(block.raw)
    conversion.record(LossCode.BLOCK_NOT_CARRIED, f"{block.kind.value} into {WIRE_FORMAT}")
    return None


def _reasoning_to_anthropic(
    block: ContentBlock,
    conversion: Conversion,
    *,
    bridge_for_client: bool,
) -> dict[str, Any] | None:
    """Render reasoning natively, or put provider-specific state in a client carrier."""
    content = block.reasoning
    if content is None:
        conversion.record(LossCode.BLOCK_NOT_CARRIED, "reasoning block has no typed content")
        return None
    try:
        return reasoning_to_anthropic(content, bridge_for_client=bridge_for_client)
    except ReasoningNotPortable:
        state = content.state
        source = state.format.value if state is not None else content.source_format
        conversion.record(
            LossCode.REASONING_STATE_NOT_PORTABLE,
            f"{source} cannot be written to an Anthropic upstream",
        )
        return None


def _thinking_profile_detail(target: TranslationTarget, *, reason: str | None = None) -> str:
    model = target.model_id or "<unknown>"
    pattern = target.thinking_profile_pattern or "<none>"
    detail = f"resolved_model={model}; pattern={pattern}"
    return f"{detail}; reason={reason}" if reason is not None else detail


def _thinking_profile_refusal(
    conversion: Conversion,
    target: TranslationTarget,
    message: str,
    *,
    code: str,
    field_path: str,
) -> TranslationRefused:
    conversion.observe(
        ConversionFactCode.THINKING_PROFILE_REJECTED,
        _thinking_profile_detail(target, reason=code),
    )
    return TranslationRefused(
        message,
        code=code,
        field_path=field_path,
        facts=tuple(conversion.facts),
    )


def render_anthropic_thinking(
    intent: ThinkingEffortIntent,
    target: TranslationTarget,
    *,
    max_tokens: int | None,
    conversion: Conversion | None = None,
) -> dict[str, Any]:
    """Render thinking only from the resolved target's configured profile."""
    observed = conversion if conversion is not None else Conversion()
    profile = target.thinking_profile
    if profile is None:
        raise _thinking_profile_refusal(
            observed,
            target,
            "no thinking profile matches the resolved model",
            code="thinking-profile-missing",
            field_path="reasoning",
        )
    observed.observe(
        ConversionFactCode.THINKING_PROFILE_SELECTED,
        _thinking_profile_detail(target),
    )
    if not intent.enabled:
        if not profile.can_disable:
            raise _thinking_profile_refusal(
                observed,
                target,
                "target model cannot disable thinking",
                code="thinking-disable-not-supported",
                field_path="reasoning.effort",
            )
        if profile.disabled_max_effort is not None and EFFORT_LADDER.index("high") > EFFORT_LADDER.index(profile.disabled_max_effort):
            raise _thinking_profile_refusal(
                observed,
                target,
                "target model cannot disable thinking at its effective effort",
                code="thinking-disable-effort-not-supported",
                field_path="reasoning.effort",
            )
        return {"type": "disabled"}

    for mode in profile.modes:
        if mode == "adaptive":
            return {"type": "adaptive"}
        budget = profile.manual_budget_tokens
        if mode == "enabled" and budget is not None and budget >= 1024 and max_tokens is not None and budget < max_tokens:
            return {"type": "enabled", "budget_tokens": budget}
    raise _thinking_profile_refusal(
        observed,
        target,
        "target thinking profile has no renderable mode",
        code="thinking-mode-not-renderable",
        field_path="reasoning",
    )


def _apply_responses_thinking(
    payload: dict[str, Any],
    request: SemanticRequest,
    target: TranslationTarget,
) -> None:
    intent = request.thinking_effort
    if request.source_format != RESPONSES_WIRE_FORMAT or intent is None:
        return

    payload["thinking"] = render_anthropic_thinking(
        intent,
        target,
        max_tokens=request.max_output_tokens,
        conversion=request.conversion,
    )
    if not intent.enabled or intent.effort is None:
        return

    desired = intent.effort
    if desired == "minimal":
        request.conversion.record(
            LossCode.REASONING_INTENT_APPROXIMATED,
            "Responses effort minimal was approximated to Anthropic low",
        )
        desired = "low"
    elif desired not in ANTHROPIC_EFFORTS:
        raise TranslationRefused(
            "invalid Responses reasoning effort",
            code="effort-invalid",
            field_path="reasoning.effort",
        )

    resolution = align_anthropic_effort(desired, target.reasoning_efforts)
    if resolution.effort is None:
        request.conversion.record(
            LossCode.REASONING_INTENT_NOT_CARRIED,
            f"{desired} effort was not sent to Anthropic: {resolution.reason}",
        )
        return

    existing = payload.get("output_config")
    output = cast(dict[str, Any], existing) if isinstance(existing, dict) else {}
    output["effort"] = resolution.effort
    payload["output_config"] = output
    if resolution.approximated:
        request.conversion.record(
            LossCode.REASONING_INTENT_APPROXIMATED,
            resolution.reason or f"effort {desired} was sent as {resolution.effort}",
        )


def to_anthropic_messages(
    request: SemanticRequest,
    target_model: TranslationTarget | None = None,
    *,
    options: TranslationOptions | None = None,
) -> dict[str, Any]:
    if options is not None and target_model is None:
        target_model = options.target
    target = target_model or TranslationTarget()
    messages: list[dict[str, Any]] = []
    for message in request.messages:
        rendered = [
            block
            for block in (
                _block_to_anthropic(
                    b,
                    request.conversion,
                    bridge_for_client=False,
                )
                for b in message.blocks
            )
            if block is not None
        ]
        messages.append({"role": message.role, "content": rendered})

    payload: dict[str, Any] = {"model": request.model, "messages": messages}
    if request.system:
        payload["system"] = _system_value(request.system)
    if request.tools:
        payload["tools"] = request.tools
    if request.stream:
        payload["stream"] = True
    if request.max_output_tokens is not None:
        payload["max_tokens"] = request.max_output_tokens
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    payload.update(request.nested_extensions_for(WIRE_FORMAT))
    _restore_thinking(payload, request)
    _apply_responses_thinking(payload, request, target)
    _restore_tool_choice(payload, request)
    chat_stop = request.unknown_fields.get("stop")
    chat_stop_supported = request.source_format == CHAT_COMPLETIONS_WIRE_FORMAT and (
        isinstance(chat_stop, str)
        or (
            isinstance(chat_stop, list)
            and all(
                isinstance(item, str) for item in cast(list[Any], chat_stop)
            )
        )
    )
    if chat_stop_supported:
        payload["stop_sequences"] = (
            [chat_stop] if isinstance(chat_stop, str) else list(cast(list[Any], chat_stop))
        )
    payload.update(
        request.unknown_fields_for(
            WIRE_FORMAT,
            excluded=frozenset({"stop"}) if chat_stop_supported else frozenset(),
        )
    )
    return payload


def _restore_thinking(payload: dict[str, Any], request: SemanticRequest) -> None:
    """Rebuild only an Anthropic-origin request; rendering a Responses intent against a target profile belongs to Task 4."""
    intent = request.thinking_effort
    if intent is None or request.source_format != WIRE_FORMAT:
        return

    if "thinking" in request.nested_extensions:
        existing_thinking = payload.get("thinking")
        thinking = (
            cast(dict[str, Any], existing_thinking)
            if isinstance(existing_thinking, dict)
            else {}
        )
        if not intent.enabled:
            thinking["type"] = "disabled"
        elif "budget_tokens" in thinking:
            thinking["type"] = "enabled"
        else:
            thinking["type"] = "adaptive"
        payload["thinking"] = thinking

    if intent.effort_source is EffortSource.ANTHROPIC_TOP_LEVEL and intent.effort is not None:
        existing_output = payload.get("output_config")
        output = cast(dict[str, Any], existing_output) if isinstance(existing_output, dict) else {}
        output["effort"] = intent.effort
        payload["output_config"] = output


def _restore_tool_choice(payload: dict[str, Any], request: SemanticRequest) -> None:
    """Render the intent without relaxing a selection the target cannot honor."""
    crossing = request.source_format != WIRE_FORMAT
    intent = request.tool_choice
    if intent is None:
        if crossing and "tool_choice" in request.extensions:
            raise ToolChoiceNotSupported("tool_choice has no supported Anthropic translation")
        return
    if intent.mode in {"auto", "any", "none"}:
        choice: dict[str, Any] = {"type": intent.mode}
    elif intent.mode == "tool" and intent.name:
        choice = {"type": "tool", "name": intent.name}
    else:
        raise ToolChoiceNotSupported(f"{intent.mode} tool choice has no Anthropic spelling")
    if crossing:
        if not payload.get("tools"):
            if intent.mode in {"any", "tool"}:
                raise ToolChoiceNotSupported("a forced tool choice requires declared tools")
            return
        if intent.mode == "tool" and not any(
            tool.get("name") == intent.name for tool in request.tools
        ):
            raise ToolChoiceNotSupported(f"{intent.name} is not declared by the tools this request sends")
    if intent.disable_parallel is not None:
        choice["disable_parallel_tool_use"] = intent.disable_parallel
    payload["tool_choice"] = choice
