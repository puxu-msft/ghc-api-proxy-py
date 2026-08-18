from typing import Any, cast


def signature_delta_for_start(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("type") != "content_block_start":
        return None
    block = event.get("content_block")
    if not isinstance(block, dict):
        return None
    typed_block = cast(dict[str, Any], block)
    if typed_block.get("type") != "thinking":
        return None
    signature = typed_block.get("signature")
    if not isinstance(signature, str) or not signature:
        return None
    return {
        "type": "content_block_delta",
        "index": event.get("index"),
        "delta": {"type": "signature_delta", "signature": signature},
    }
