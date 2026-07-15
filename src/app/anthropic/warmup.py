from typing import Any, Literal, cast

type WarmupPolicy = Literal["allow", "reject", "drop", "fake"]


def is_warmup_request(payload: dict[str, Any]) -> bool:
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return False
    first: object = cast(list[object], messages)[0]
    if not isinstance(first, dict):
        return False
    typed_first = cast(dict[str, Any], first)
    if typed_first.get("role") != "user":
        return False
    content = typed_first.get("content")
    if isinstance(content, str):
        return content == "Warmup"
    if isinstance(content, list):
        for block in cast(list[object], content):
            if not isinstance(block, dict):
                continue
            typed_block = cast(dict[str, Any], block)
            if typed_block.get("type") == "text" and typed_block.get("text") == "Warmup":
                return True
    return False


def apply_warmup_policy(
    payload: dict[str, Any],
    policy: WarmupPolicy,
) -> dict[str, Any] | None:
    if not is_warmup_request(payload) or policy == "allow":
        return None
    if policy == "reject":
        return {"error": {"type": "rate_limit_error", "message": "Warmup rejected"}}
    content = [] if policy == "drop" else [{"type": "text", "text": "Cache warmed."}]
    return {
        "id": "msg_warmup",
        "type": "message",
        "role": "assistant",
        "model": payload.get("model", "unknown"),
        "content": content,
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }