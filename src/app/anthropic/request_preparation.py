import copy
from dataclasses import dataclass
from typing import Any, cast

from app.anthropic.features import build_anthropic_beta_headers
from app.anthropic.message_tools import preprocess_tools
from app.anthropic.thinking.destack import destack_content


@dataclass(frozen=True, slots=True)
class PreparedRequest:
    wire: dict[str, Any]
    headers: dict[str, str]


def prepare_anthropic_request(
    payload: dict[str, Any],
    *,
    tool_search: bool = False,
    non_deferred_tools: tuple[str, ...] = (),
    apply_payload_rewrites: bool = True,
) -> PreparedRequest:
    wire = copy.deepcopy(payload)
    wire.pop("inference_geo", None)
    tools = wire.get("tools")
    if apply_payload_rewrites and isinstance(tools, list):
        wire["tools"] = preprocess_tools(
            cast(list[dict[str, Any]], tools),
            inject_tool_search=tool_search,
            non_deferred=non_deferred_tools,
        )
    if apply_payload_rewrites:
        messages = cast(list[dict[str, Any]], wire.get("messages", []))
        for message in messages:
            if message.get("role") != "assistant" or not isinstance(message.get("content"), list):
                continue
            content, _ = destack_content(message["content"], "move_blocks")
            message["content"] = content
    headers = {"anthropic-version": "2023-06-01"}
    headers.update(
        build_anthropic_beta_headers(
            str(wire.get("model", "")),
            tool_search=tool_search,
        )
    )
    return PreparedRequest(wire=wire, headers=headers)