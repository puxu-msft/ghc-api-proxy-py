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

from app.pipeline.translation_driver.content import BlockKind, ContentBlock
from app.pipeline.translation_driver.reasoning_bridge import read_chat_reasoning
from app.pipeline.translation_driver.responses import SemanticResponse
from app.pipeline.translation_driver.semantic import (
    Conversion,
    LossCode,
    SemanticRequest,
    TranslationTarget,
)

WIRE_FORMAT = "openai-chat-completions"

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
    request: SemanticRequest, target: TranslationTarget | None = None
) -> dict[str, Any]:
    """Render the intermediate form as a Chat Completions request body.

    `target` is accepted for the writer signature and unused: this wire publishes
    no reasoning-effort vocabulary to align with, so there is nothing a resolved
    model's capabilities would change here.
    """
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
        messages.extend(_chat_messages(message, conversion))

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

    # `tool_choice` and `stop_sequences` ride in `extensions`, because no translator
    # claims them generically. This wire *can* say both, so they are claimed here —
    # popped before `extensions_for`, which would otherwise record their loss and
    # drop them, turning "must call a tool" into "may call one".
    tool_choice = request.extensions.pop("tool_choice", None)
    mapped_choice, parallel_tool_calls = _chat_tool_choice(tool_choice, conversion)
    if mapped_choice is not None:
        body["tool_choice"] = mapped_choice
    if parallel_tool_calls is not None:
        body["parallel_tool_calls"] = parallel_tool_calls
    stop_sequences = request.extensions.pop("stop_sequences", None)
    if isinstance(stop_sequences, list) and stop_sequences:
        body["stop"] = stop_sequences
    body.update(request.extensions_for(WIRE_FORMAT))

    if request.reasoning is not None:
        conversion.record(
            LossCode.REASONING_INTENT_NOT_CARRIED,
            "Chat Completions publishes no reasoning field this proxy has measured; "
            "the request's reasoning intent was not sent",
        )
    return body


def _chat_messages(
    message: Any, conversion: Conversion
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
            "parameters": tool.get("input_schema", {}),
        },
    }


def _chat_tool_choice(
    value: object, conversion: Conversion
) -> tuple[object, bool | None]:
    """An Anthropic `tool_choice` in chat's spelling, plus `parallel_tool_calls`.

    The second element is chat's own `parallel_tool_calls` key, which is a body
    field of its own rather than part of `tool_choice` — `None` when the request
    said nothing. Anthropic's `any` and OpenAI's `required` are the same claim —
    some tool, no preference — and Anthropic's `disable_parallel_tool_use` is the
    inverse of chat's `parallel_tool_calls`. A shape this cannot read is recorded
    and dropped rather than guessed at: a forced choice silently becoming a free
    one reverses an instruction.
    """
    if value is None:
        return None, None
    if isinstance(value, str):
        return (value if value in ("auto", "none", "required") else None), None
    if not isinstance(value, dict):
        conversion.record(
            LossCode.EXTENSIONS_NOT_CARRIED, f"tool_choice of unreadable shape: {value!r}"
        )
        return None, None
    choice = cast(dict[str, Any], value)
    choice_type = choice.get("type")
    mapped: object
    if choice_type == "auto":
        mapped = "auto"
    elif choice_type == "any":
        mapped = "required"
    # `type: "tool"` is Anthropic's spelling of a named forced call, `type: "function"`
    # is Responses'; both mean the same and both are accepted, because the writer
    # serves whichever of the two readers produced the intermediate form.
    elif choice_type in ("tool", "function") and isinstance(choice.get("name"), str):
        mapped = {"type": "function", "function": {"name": choice["name"]}}
    else:
        conversion.record(
            LossCode.EXTENSIONS_NOT_CARRIED, f"tool_choice {choice_type!r} has no Chat spelling"
        )
        return None, None
    parallel = False if choice.get("disable_parallel_tool_use") is True else None
    return mapped, parallel


def from_chat_completions_response(
    payload: Mapping[str, Any],
    *,
    client_search_tool: str = "",
    hosted_web_search_expected: bool = False,
) -> SemanticResponse:
    """Read a whole `chat.completion` object into the intermediate form."""
    del client_search_tool, hosted_web_search_expected
    response = SemanticResponse(
        id=str(payload.get("id", "")),
        model=str(payload.get("model", "")),
    )
    choices = payload.get("choices")
    choice = dict[str, Any]()
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        choice = dict[str, Any](cast(dict[str, Any], choices[0]))
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

    usage = payload.get("usage")
    if isinstance(usage, dict):
        response.usage = chat_usage_to_anthropic(cast(dict[str, Any], usage))

    finish = choice.get("finish_reason")
    response.stop_reason = CHAT_STOP_REASONS.get(str(finish), str(finish) or END_TURN)
    return response


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
