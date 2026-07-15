import copy
from dataclasses import dataclass
from typing import Any

from app.anthropic.features import build_anthropic_beta_headers
from app.anthropic.thinking.destack import destack_content


@dataclass(frozen=True, slots=True)
class PreparedRequest:
    wire: dict[str, Any]
    headers: dict[str, str]


def prepare_anthropic_request(payload: dict[str, Any]) -> PreparedRequest:
    wire = copy.deepcopy(payload)
    wire.pop("inference_geo", None)
    messages = wire.get("messages", [])
    for message in messages:
        if message.get("role") != "assistant" or not isinstance(message.get("content"), list):
            continue
        content, _ = destack_content(message["content"], "move_blocks")
        message["content"] = content
    headers = {"anthropic-version": "2023-06-01"}
    headers.update(build_anthropic_beta_headers(str(wire.get("model", ""))))
    return PreparedRequest(wire=wire, headers=headers)