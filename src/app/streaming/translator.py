import copy
from typing import Any, cast


def translate_chat_event_to_responses(event: dict[str, Any]) -> dict[str, Any] | None:
    choices = event.get("choices")
    if not isinstance(choices, list) or not choices:
        return copy.deepcopy(event)
    choice = cast(dict[str, Any], choices[0])
    delta = choice.get("delta", {})
    if isinstance(delta.get("content"), str):
        return {
            "type": "response.output_text.delta",
            "delta": delta["content"],
            "source": copy.deepcopy(event),
        }
    if choice.get("finish_reason") is not None:
        return {
            "type": "response.completed",
            "finish_reason": choice["finish_reason"],
            "source": copy.deepcopy(event),
        }
    return None
