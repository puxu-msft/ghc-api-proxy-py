import copy
from dataclasses import dataclass
from typing import Any, cast

from app.anthropic.features import build_anthropic_beta_headers
from app.anthropic.message_tools import preprocess_tools
from app.anthropic.thinking.destack import destack_content
from app.anthropic.thinking.reasoning_carrier import is_direct_messages_synthetic_signature


@dataclass(frozen=True, slots=True)
class PreparedRequest:
    wire: dict[str, Any]
    headers: dict[str, str]


def prepare_anthropic_request(
    payload: dict[str, Any],
    *,
    tool_search: bool = False,
    non_deferred_tools: tuple[str, ...] = (),
    apply_tool_preprocessing: bool = True,
    apply_thinking_destack: bool = True,
) -> PreparedRequest:
    wire = copy.deepcopy(payload)
    wire.pop("inference_geo", None)
    tools = wire.get("tools")
    if apply_tool_preprocessing and isinstance(tools, list):
        wire["tools"] = preprocess_tools(
            cast(list[dict[str, Any]], tools),
            inject_tool_search=tool_search,
            non_deferred=non_deferred_tools,
        )
    messages = cast(list[dict[str, Any]], wire.get("messages", []))
    for message in messages:
        content_value: object = message.get("content")
        if not isinstance(content_value, list):
            continue
        content = cast(list[object], content_value)
        message["content"] = [
            block
            for block in content
            if not _is_synthetic_thinking_block(block)
        ]
    messages[:] = [
        message
        for message in messages
        if not isinstance(message.get("content"), list) or message["content"]
    ]
    if apply_thinking_destack:
        for message in messages:
            if message.get("role") != "assistant" or not isinstance(message.get("content"), list):
                continue
            destacked, _ = destack_content(message["content"], "move_blocks")
            message["content"] = destacked
    headers = {"anthropic-version": "2023-06-01"}
    headers.update(
        build_anthropic_beta_headers(
            str(wire.get("model", "")),
            tool_search=tool_search,
        )
    )
    return PreparedRequest(wire=wire, headers=headers)


def _is_synthetic_thinking_block(block: object) -> bool:
    if not isinstance(block, dict):
        return False
    typed_block = cast(dict[str, object], block)
    if typed_block.get("type") != "thinking":
        return False
    signature = typed_block.get("signature")
    return isinstance(signature, str) and is_direct_messages_synthetic_signature(signature)
