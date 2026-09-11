"""The OpenAI Chat Completions translators: the wire this one speaks and the
intermediate form it meets.

Chat Completions is the only wire the CodeBuddy upstream answers, so this module is
what lets an Anthropic- or Responses-speaking client reach it: the request side
renders the intermediate form into a chat body, and the response side reads a
`chat.completion` object back into the intermediate form. The streaming half —
reading chat's SSE chunks into blocks — lives beside the other assemblers in
`app.pipeline.delivery.formats` and imports its shared mappings from here, so the
buffered and streaming halves of this leg cannot describe one fact differently.

The request side is deliberately a *writer*, not a second client format: nothing
here talks to the network, and nothing here is allowed to invent a field the
intermediate form did not carry.
"""

import json
from collections.abc import Mapping
from typing import Any, cast

from app.pipeline.translation_driver.content import (
    BlockKind,
    ContentBlock,
    SemanticMessage,
)
from app.pipeline.translation_driver.options import TranslationOptions
from app.pipeline.translation_driver.reasoning import EffortSource
from app.pipeline.translation_driver.reasoning_bridge import read_chat_reasoning
from app.pipeline.translation_driver.responses import (
    OpaqueResponsePayload,
    SemanticResponse,
)
from app.pipeline.translation_driver.semantic import (
    Conversion,
    LossCode,
    SemanticRequest,
    SystemBlock,
    ToolChoiceNotSupported,
    TranslationRefused,
    TranslationTarget,
)
from app.pipeline.translation_driver.tool_choice import intent_from_chat_tool_choice

WIRE_FORMAT = "openai-chat-completions"
RESPONSES_WIRE_FORMAT = "openai-responses"

TEXT = "text"
TOOL_CALLS = "tool_calls"
REASONING_CONTENT = "reasoning_content"

END_TURN = "end_turn"
MAX_TOKENS = "max_tokens"
TOOL_USE_STOP = "tool_use"

# Chat Completions' `finish_reason` → the intermediate form's stop reason, said in
# Anthropic's vocabulary because `SemanticResponse.stop_reason` is rendered by the
# Anthropic response writer. `content_filter` has no Anthropic spelling and is
# deliberately not flattened into `end_turn` — a moderation cut is not a turn the
# model chose to end, and the house rule (see the Responses reader) is to carry
# upstream's own word unmapped rather than invent a synonym. Shared with the
# streaming assembler; the buffered and streaming halves of one leg answer this
# question once.
CHAT_STOP_REASONS = {
    "stop": END_TURN,
    "tool_calls": TOOL_USE_STOP,
    "length": MAX_TOKENS,
}

_PASSTHROUGH_KEYS = frozenset(
    {
        "model",
        "messages",
        "tools",
        "stream",
        "max_tokens",
        "max_completion_tokens",
        "temperature",
        "parallel_tool_calls",
    }
)


def _supported_chat_stop(value: object) -> bool:
    return isinstance(value, str) or (
        isinstance(value, list)
        and all(isinstance(item, str) for item in cast(list[Any], value))
    )


def _empty_messages_refusal(request: SemanticRequest) -> TranslationRefused:
    if request.source_format == RESPONSES_WIRE_FORMAT:
        return TranslationRefused(
            "input must be non-empty",
            code="input-empty",
            field_path="input",
        )
    return TranslationRefused(
        "messages must be non-empty",
        code="messages-empty",
        field_path="messages",
    )


def chat_usage_to_anthropic(usage: Mapping[str, Any]) -> dict[str, Any]:
    """A Chat Completions usage object in the keys the Anthropic writer renders.

    `prompt_tokens` includes what was served from cache, exactly as Responses'
    `input_tokens` does, so `cached_tokens` becomes `cache_read_input_tokens` and
    the fresh-input figure comes out right instead of reading a mostly-cached
    prompt as a full-price one. A malformed usage returns empty rather than
    failing the reply, matching `_anthropic_usage` on the Responses leg.
    """
    try:
        converted: dict[str, Any] = {
            "input_tokens": int(usage["prompt_tokens"]),
            "output_tokens": int(usage["completion_tokens"]),
        }
    except (KeyError, TypeError, ValueError):
        return {}
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        raw_cached = cast(dict[str, Any], details).get("cached_tokens", 0)
        try:
            cached = int(cast(int, raw_cached))
        except (TypeError, ValueError):
            cached = 0
        if cached:
            converted["cache_read_input_tokens"] = cached
    return converted


def to_openai_chat_completions(
    request: SemanticRequest,
    target_model: TranslationTarget | None = None,
    *,
    options: TranslationOptions | None = None,
) -> dict[str, Any]:
    """Render the intermediate form as a Chat Completions request body.

    `target_model` is accepted for the writer signature and unused: this wire publishes
    no reasoning-effort vocabulary to align with, so there is nothing a resolved
    model's capabilities would change here.
    """
    del target_model, options
    conversion = request.conversion
    messages: list[dict[str, Any]] = []
    if request.system:
        if any(block.metadata for block in request.system):
            conversion.record(
                LossCode.SYSTEM_METADATA_NOT_CARRIED,
                "system block metadata (e.g. cache_control) has no Chat Completions spelling",
            )
        system_text = "\n".join(block.text for block in request.system if block.text)
        if system_text:
            messages.append({"role": "system", "content": system_text})

    for message in request.messages:
        messages.extend(
            _chat_messages(
                message,
                conversion,
                preserve_unknown=request.source_format == WIRE_FORMAT,
            )
        )

    body: dict[str, Any] = {
        "model": request.model,
        "messages": messages,
        "stream": request.stream,
    }
    if request.max_output_tokens is not None:
        body["max_tokens"] = request.max_output_tokens
    if request.temperature is not None:
        body["temperature"] = request.temperature
    if request.tools:
        body["tools"] = [_chat_tool(tool) for tool in request.tools]

    # Tool selection was claimed by the reader; stop_sequences is still this writer's extension.
    mapped_choice, parallel_tool_calls = _chat_tool_choice(request)
    if mapped_choice is not None:
        body["tool_choice"] = mapped_choice
    if parallel_tool_calls is not None:
        body["parallel_tool_calls"] = parallel_tool_calls
    if not messages:
        raise _empty_messages_refusal(request)

    stop = request.unknown_fields.get("stop")
    stop_sequences = request.unknown_fields.get("stop_sequences")
    if _supported_chat_stop(stop):
        body["stop"] = stop
    elif isinstance(stop_sequences, list) and stop_sequences:
        body["stop"] = stop_sequences
    body.update(
        request.unknown_fields_for(
            WIRE_FORMAT,
            excluded=frozenset({"stop", "stop_sequences", "tool_choice"}),
        )
    )

    intent = request.thinking_effort
    if intent is not None and (
        intent.effort_source is not EffortSource.ANTHROPIC_DEFAULT
        or "thinking" in request.nested_extensions
    ):
        conversion.record(
            LossCode.REASONING_INTENT_NOT_CARRIED,
            "Chat Completions publishes no reasoning field this proxy has measured; "
            "the request's reasoning intent was not sent",
        )
    return body


def _chat_content_blocks(value: object, conversion: Conversion) -> tuple[ContentBlock, ...]:
    if isinstance(value, str):
        return (ContentBlock(BlockKind.TEXT, text=value),)
    if not isinstance(value, list):
        return ()
    blocks: list[ContentBlock] = []
    for raw in cast(list[object], value):
        if not isinstance(raw, Mapping):
            conversion.warn(
                "malformed-content-part",
                source_format=WIRE_FORMAT,
                field_path="messages[].content",
                detail="non-object content part skipped",
            )
            continue
        part = dict[str, Any](cast(Mapping[str, Any], raw))
        kind = part.get("type")
        if kind == "text":
            blocks.append(ContentBlock(BlockKind.TEXT, text=str(part.get("text", "")), raw=part))
        elif kind == "image_url":
            blocks.append(ContentBlock(BlockKind.IMAGE, raw=part))
        else:
            blocks.append(ContentBlock(BlockKind.UNKNOWN, raw=part))
    return tuple(blocks)


def _chat_message(raw: Mapping[str, Any], conversion: Conversion) -> SemanticMessage:
    message = dict[str, Any](raw)
    role = str(message.get("role", ""))
    blocks: list[ContentBlock] = list(
        _chat_content_blocks(message.get("content"), conversion)
    )
    reasoning = message.get(REASONING_CONTENT)
    if isinstance(reasoning, str) and reasoning:
        blocks.insert(
            0,
            ContentBlock(BlockKind.REASONING, reasoning=read_chat_reasoning(reasoning)),
        )
    raw_calls = message.get("tool_calls")
    if isinstance(raw_calls, list):
        for call in cast(list[object], raw_calls):
            if isinstance(call, Mapping):
                blocks.append(
                    _tool_use_block(dict[str, Any](cast(Mapping[str, Any], call)), conversion)
                )
    if role == "tool":
        blocks = [
            ContentBlock(
                BlockKind.TOOL_RESULT,
                call_id=str(message.get("tool_call_id", "")),
                output=message.get("content"),
                raw=message,
            )
        ]
    return SemanticMessage(role=role, blocks=tuple(blocks), raw=message)


def from_openai_chat_completions(
    payload: Mapping[str, Any],
    *,
    options: TranslationOptions | None = None,
    source_headers: Mapping[str, str] | None = None,
    translated: bool = False,
) -> SemanticRequest:
    """Decode a Chat Completions request into the shared semantic IR."""
    del source_headers, translated
    conversion = Conversion()
    raw_messages = payload.get("messages")
    messages = [
        _chat_message(cast(Mapping[str, Any], raw), conversion)
        for raw in cast(list[object], raw_messages)
        if isinstance(raw, Mapping)
        and str(cast(Mapping[str, Any], raw).get("role", "")) not in {"system", "developer"}
    ] if isinstance(raw_messages, list) else []
    system: list[dict[str, Any]] = []
    if isinstance(raw_messages, list):
        for raw in cast(list[object], raw_messages):
            if not isinstance(raw, Mapping):
                continue
            message = cast(Mapping[str, Any], raw)
            if str(message.get("role", "")) in {"system", "developer"}:
                content = message.get("content")
                if isinstance(content, str):
                    system.append({"type": "text", "text": content})
                elif isinstance(content, list):
                    for part in cast(list[object], content):
                        if not isinstance(part, Mapping):
                            continue
                        part_mapping = cast(Mapping[str, Any], part)
                        if part_mapping.get("type") == "text":
                            system.append(
                                {
                                    "type": "text",
                                    "text": str(part_mapping.get("text", "")),
                                }
                            )

    tools: list[dict[str, Any]] = []
    raw_tools = payload.get("tools")
    if isinstance(raw_tools, list):
        for raw in cast(list[object], raw_tools):
            if not isinstance(raw, Mapping):
                continue
            tool = dict[str, Any](cast(Mapping[str, Any], raw))
            function = tool.get("function")
            if tool.get("type") == "function" and isinstance(function, Mapping):
                fn = dict[str, Any](cast(Mapping[str, Any], function))
                tools.append(
                    {
                        "name": fn.get("name", ""),
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {}),
                    }
                )
            else:
                tools.append(tool)

    request = SemanticRequest(
        model=str(payload.get("model", "")),
        system=[
            SystemBlock(text=str(item["text"]))
            for item in system
        ],
        messages=messages,
        tools=tools,
        stream=bool(payload.get("stream", False)),
        source_format=WIRE_FORMAT,
        conversion=conversion,
    )
    max_tokens = payload.get("max_tokens", payload.get("max_completion_tokens"))
    if isinstance(max_tokens, int):
        request.max_output_tokens = max_tokens
    temperature = payload.get("temperature")
    if isinstance(temperature, int | float):
        request.temperature = float(temperature)
    request.tool_choice = intent_from_chat_tool_choice(
        payload.get("tool_choice"), payload.get("parallel_tool_calls")
    )
    request.extensions = {
        key: value for key, value in payload.items() if key not in _PASSTHROUGH_KEYS
    }
    if request.tool_choice is not None:
        request.extensions.pop("tool_choice", None)
    if request.tool_choice is None and "tool_choice" in payload:
        request.extensions["tool_choice"] = payload["tool_choice"]
    return request


def _chat_messages(
    message: Any,
    conversion: Conversion,
    *,
    preserve_unknown: bool = False,
) -> list[dict[str, Any]]:
    """Render one intermediate message as one or more chat messages.

    A user turn holding `tool_result` blocks becomes `role: "tool"` messages, one
    per result, in block order — the chat wire's rule that a tool answer follows
    the call it answers is the same rule the intermediate form preserves.
    """
    blocks = getattr(message, "blocks", ())
    role = getattr(message, "role", "")
    rendered: list[dict[str, Any]] = []
    if role == "user":
        text_parts: list[str] = []
        tool_messages: list[dict[str, Any]] = []
        for block in blocks:
            if block.kind is BlockKind.TEXT:
                text_parts.append(block.text)
            elif block.kind is BlockKind.TOOL_RESULT:
                tool_messages.append(_chat_tool_message(block, conversion))
            elif block.kind is BlockKind.IMAGE:
                conversion.record(
                    LossCode.BLOCK_NOT_CARRIED,
                    "image block has no rendering on Chat Completions this proxy has measured",
                )
            else:
                if preserve_unknown and block.raw:
                    return [dict(block.raw)]
                conversion.record(
                    LossCode.BLOCK_NOT_CARRIED, f"{block.kind.value} block in a user turn"
                )
        # Block order is conversation order: a question written before a tool
        # answer arrived stays before it.
        rendered.extend(tool_messages)
        if text_parts:
            rendered.append({"role": "user", "content": "".join(text_parts)})
        return rendered

    if role == "assistant":
        text_parts = []
        tool_calls: list[dict[str, Any]] = []
        for block in blocks:
            if block.kind is BlockKind.TEXT:
                text_parts.append(block.text)
            elif block.kind is BlockKind.TOOL_USE:
                tool_calls.append(
                    {
                        "id": block.call_id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(
                                block.arguments if block.arguments is not None else {},
                                ensure_ascii=False,
                            ),
                        },
                    }
                )
            elif block.kind is BlockKind.REASONING:
                # Reasoning history has no portable spelling here: its opaque state
                # belongs to the wire that issued it, and the readable text is the
                # model's own scratch work, not a turn a client resubmits.
                conversion.record(
                    LossCode.REASONING_STATE_NOT_PORTABLE,
                    "reasoning block dropped crossing to Chat Completions",
                )
            else:
                conversion.record(
                    LossCode.BLOCK_NOT_CARRIED, f"{block.kind.value} block in an assistant turn"
                )
        assistant: dict[str, Any] = {"role": "assistant", "content": "".join(text_parts) or None}
        if tool_calls:
            assistant["tool_calls"] = tool_calls
        return [assistant]

    # Roles the intermediate form carried but this writer does not model.
    if preserve_unknown and getattr(message, "raw", None):
        return [dict(cast(Mapping[str, Any], message.raw))]
    conversion.record(LossCode.ITEM_NOT_CARRIED, f"message with role {role!r}")
    return []


def _chat_tool_message(block: ContentBlock, conversion: Conversion) -> dict[str, Any]:
    output = block.output
    if isinstance(output, list):
        # A structured tool result flattens to its text: the chat wire's tool
        # message carries a string. Recorded, because images or documents inside
        # the result are gone, not merged.
        conversion.record(
            LossCode.TOOL_RESULT_CONTENT_FLATTENED,
            f"tool result for {block.call_id!r} carried structured content",
        )
        output = "".join(
            str(part.get("text", ""))
            for part in cast(list[dict[str, Any]], output)
            if part.get("type") == "text"
        )
    if not isinstance(output, str):
        output = json.dumps(output, ensure_ascii=False) if output is not None else ""
    if block.is_error:
        # The chat wire has no error flag on a tool message. The prefix is the same
        # rendering the Responses bridge uses, so one history renders one shape on
        # whichever leg it crosses; the addition is recorded because the model is
        # now reading words the client did not write.
        conversion.record(
            LossCode.SYNTHETIC_TURN_ADDED,
            f"tool result for {block.call_id!r} was an error; rendered as a [tool_error] prefix",
        )
        output = f"[tool_error] {output}"
    return {"role": "tool", "tool_call_id": block.call_id, "content": output}


def _chat_tool(tool: Mapping[str, Any]) -> dict[str, Any]:
    """One tool declaration in chat's `{type: function, function: …}` shape."""
    tool = cast(dict[str, Any], tool)
    return {
        "type": "function",
        "function": {
            "name": tool.get("name", ""),
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", tool.get("parameters", {})),
        },
    }


def _chat_tool_choice(request: SemanticRequest) -> tuple[object, bool | None]:
    """Render the shared intent, never re-parse an unclaimed foreign extension."""
    crossing = request.source_format != WIRE_FORMAT
    intent = request.tool_choice
    if intent is None:
        if crossing and "tool_choice" in request.unknown_fields:
            raise ToolChoiceNotSupported("tool_choice has no supported Chat Completions translation")
        if not crossing and "tool_choice" in request.unknown_fields:
            return request.unknown_fields["tool_choice"], None
        return None, None
    if crossing and not request.tools:
        if intent.mode in {"any", "tool"}:
            raise ToolChoiceNotSupported("a forced tool choice requires declared tools")
        if intent.mode in {"auto", "none"}:
            return None, None
    mapped: object
    if intent.mode in {"auto", "none"}:
        mapped = intent.mode
    elif intent.mode == "any":
        mapped = "required"
    elif intent.mode == "tool" and intent.name:
        if crossing and not any(tool.get("name") == intent.name for tool in request.tools):
            raise ToolChoiceNotSupported(f"{intent.name} is not declared by the tools this request sends")
        mapped = {"type": "function", "function": {"name": intent.name}}
    else:
        raise ToolChoiceNotSupported(f"{intent.mode} tool choice has no Chat Completions spelling")
    parallel = False if intent.disable_parallel is True else None
    return mapped, parallel


def from_chat_completions_response(
    payload: Mapping[str, Any],
    *,
    options: TranslationOptions | None = None,
    client_search_tool: str = "",
    hosted_web_search_expected: bool = False,
    hand_over_stop_reasons: frozenset[str] = frozenset({"max_tokens"}),
) -> SemanticResponse:
    """Read a whole `chat.completion` object into the intermediate form."""
    # The response decoder accepts the request-lifetime snapshot for the common
    # codec interface, but Chat response semantics do not depend on any of its
    # request-only fields.
    del options, client_search_tool, hosted_web_search_expected, hand_over_stop_reasons
    response = SemanticResponse(
        id=str(payload.get("id", "")),
        model=str(payload.get("model", "")),
        source_format=WIRE_FORMAT,
    )
    for key in sorted(set(payload) - {"id", "model", "object", "choices", "usage"}):
        response.opaque_payloads.append(
            OpaqueResponsePayload(
                source_format=WIRE_FORMAT,
                field_path=key,
                payload={key: payload[key]},
                kind="top-level-field",
            )
        )
    choices = payload.get("choices")
    choice = dict[str, Any]()
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        choice = dict[str, Any](cast(dict[str, Any], choices[0]))
    elif choices:
        response.opaque_payloads.append(
            OpaqueResponsePayload(
                source_format=WIRE_FORMAT,
                field_path="choices[0]",
                payload={"value": choices[0]},
                kind="choice",
            )
        )
        response.conversion.warn(
            LossCode.OPAQUE_RESPONSE_SKIPPED.value,
            source_format=WIRE_FORMAT,
            field_path="choices[0]",
            detail="non-object choice was retained as opaque source payload",
        )
    message = dict[str, Any]()
    if isinstance(choice.get("message"), dict):
        message = dict[str, Any](cast(dict[str, Any], choice["message"]))

    blocks: list[ContentBlock] = []
    reasoning = message.get(REASONING_CONTENT)
    if isinstance(reasoning, str) and reasoning:
        # Some chat backends stream the model's scratch work in a `reasoning_content`
        # extension. Read rather than dropped: it is content the model produced.
        blocks.append(
            ContentBlock(
                BlockKind.REASONING,
                reasoning=read_chat_reasoning(reasoning),
            )
        )
    content = message.get("content")
    if isinstance(content, str) and content:
        blocks.append(ContentBlock(BlockKind.TEXT, text=content))
    raw_calls = message.get("tool_calls")
    if isinstance(raw_calls, list):
        for call in cast(list[object], raw_calls):
            if isinstance(call, dict):
                blocks.append(
                    _tool_use_block(dict[str, Any](cast(dict[str, Any], call)), response.conversion)
                )
    response.blocks = blocks
    for key in sorted(set(message) - {"role", "content", REASONING_CONTENT, "tool_calls"}):
        response.opaque_payloads.append(
            OpaqueResponsePayload(
                source_format=WIRE_FORMAT,
                field_path=f"choices[0].message.{key}",
                payload={key: message[key]},
                kind="message-field",
            )
        )

    usage = payload.get("usage")
    if isinstance(usage, dict):
        response.usage = chat_usage_to_anthropic(cast(dict[str, Any], usage))

    finish = choice.get("finish_reason")
    response.stop_reason = CHAT_STOP_REASONS.get(str(finish), str(finish) or END_TURN)
    return response


def to_openai_chat_completions_response(
    response: SemanticResponse,
    *,
    options: TranslationOptions | None = None,
) -> dict[str, Any]:
    """Encode the semantic response as a Chat Completions response."""
    del options
    message: dict[str, Any] = {"role": "assistant", "content": None}
    tool_calls: list[dict[str, Any]] = []
    reasoning: list[str] = []
    text: list[str] = []
    for block in response.blocks:
        if block.kind is BlockKind.TEXT:
            text.append(block.text)
        elif block.kind is BlockKind.REASONING and block.reasoning is not None:
            if block.reasoning.visible_text:
                reasoning.append(block.reasoning.visible_text)
        elif block.kind is BlockKind.TOOL_USE:
            tool_calls.append(
                {
                    "id": block.call_id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(
                            block.arguments if block.arguments is not None else {},
                            ensure_ascii=False,
                        ),
                    },
                }
            )
        elif block.kind in {BlockKind.IMAGE, BlockKind.UNKNOWN}:
            response.conversion.record(
                LossCode.BLOCK_NOT_CARRIED,
                f"{block.kind.value} response block has no Chat Completions spelling",
            )
            response.conversion.warn(
                "unsupported-semantic-block",
                source_format=response.source_format,
                field_path=f"blocks[{len(text) + len(tool_calls) + len(reasoning)}]",
                detail=f"Chat Completions skipped {block.kind.value} response block",
            )
    if text:
        message["content"] = "".join(text)
    if reasoning:
        message[REASONING_CONTENT] = "".join(reasoning)
    if tool_calls:
        message["tool_calls"] = tool_calls
    skipped_opaque = False
    finish_reason = {
        END_TURN: "stop",
        TOOL_USE_STOP: "tool_calls",
        MAX_TOKENS: "length",
    }.get(response.stop_reason, response.stop_reason or "stop")
    for opaque in response.opaque_payloads:
        if opaque.source_format == WIRE_FORMAT and opaque.kind == "message-field":
            message.update(opaque.copy_payload())
        elif opaque.source_format == WIRE_FORMAT and opaque.kind == "top-level-field":
            continue
        else:
            skipped_opaque = True
            detail = f"target {WIRE_FORMAT} cannot interpret opaque payload"
            response.conversion.record(LossCode.OPAQUE_RESPONSE_SKIPPED, detail)
            response.conversion.warn(
                LossCode.OPAQUE_RESPONSE_SKIPPED.value,
                source_format=opaque.source_format,
                field_path=opaque.field_path,
                detail=detail,
            )
    if skipped_opaque and not response.blocks and response.stop_reason == END_TURN:
        finish_reason = "length"
    encoded = {
        "id": response.id,
        "object": "chat.completion",
        "model": response.model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
        "usage": response.usage or None,
    }
    for opaque in response.opaque_payloads:
        if opaque.source_format == WIRE_FORMAT and opaque.kind == "top-level-field":
            encoded.update(opaque.copy_payload())
    return encoded


def _tool_use_block(call: dict[str, Any], conversion: Conversion) -> ContentBlock:
    function = dict[str, Any]()
    if isinstance(call.get("function"), dict):
        function = dict[str, Any](cast(dict[str, Any], call["function"]))
    raw_arguments = function.get("arguments", "")
    arguments: object = {}
    if isinstance(raw_arguments, str) and raw_arguments:
        try:
            arguments = json.loads(raw_arguments)
        except ValueError:
            conversion.record(
                LossCode.UPSTREAM_ERROR_NOT_INTERPRETED,
                f"tool call {call.get('id', '')!r} carried arguments that are not JSON",
            )
            arguments = {}
    return ContentBlock(
        BlockKind.TOOL_USE,
        call_id=str(call.get("id", "")),
        name=str(function.get("name", "")),
        arguments=arguments,
    )
