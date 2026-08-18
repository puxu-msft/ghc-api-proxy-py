from app.anthropic.thinking.destack import SYNTHETIC_SEPARATOR, destack_content
from app.anthropic.thinking.protection import (
    has_thinking_blocks,
    sanitize_empty_thinking,
    should_preserve_thinking_blocks,
)
from app.anthropic.thinking.quarantine import QuarantineKey, ThinkingQuarantineStore
from app.anthropic.thinking.strip_all import strip_all_thinking


def test_thinking_block_preserve_and_empty_sanitize() -> None:
    message = {
        "role": "assistant",
        "content": [
            {"type": "thinking", "thinking": "secret", "signature": "sig"},
            {"type": "thinking", "thinking": "", "signature": ""},
        ],
    }
    assert has_thinking_blocks(message) is True
    assert should_preserve_thinking_blocks(message, "preserve") is True
    content = message["content"]
    assert isinstance(content, list)
    cleaned, removed = sanitize_empty_thinking(content, "all_empty")
    assert removed == 1
    assert cleaned[0]["thinking"] == "secret"
    assert cleaned[0]["signature"] == "sig"


def test_destack_move_blocks_is_idempotent_and_preserves_thinking_order() -> None:
    content = [
        {"type": "thinking", "thinking": "a", "signature": "1"},
        {"type": "thinking", "thinking": "b", "signature": "2"},
        {"type": "text", "text": "answer"},
    ]
    first, changed = destack_content(content, "move_blocks")
    second, second_changed = destack_content(first, "move_blocks")
    assert changed is True
    assert second_changed is False
    assert first == second
    assert [block.get("thinking") for block in first if block["type"] == "thinking"] == ["a", "b"]
    assert first[1] == {"type": "text", "text": "answer"}


def test_strip_all_removes_thinking_and_synthetic_separator() -> None:
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "a", "signature": "1"},
                {"type": "text", "text": SYNTHETIC_SEPARATOR},
                {"type": "text", "text": "answer"},
            ],
        }
    ]
    stripped, removed = strip_all_thinking(messages)
    assert removed == 2
    assert stripped[0]["content"] == [{"type": "text", "text": "answer"}]


def test_l3_quarantine_uses_sliding_ttl_and_capacity() -> None:
    now = 100.0
    store = ThinkingQuarantineStore(ttl_seconds=10, max_entries=2, clock=lambda: now)
    key = QuarantineKey("session", "")
    store.record(key)
    now = 105.0
    assert store.is_poisoned(key) is True
    now = 112.0
    assert store.is_poisoned(key) is True
    now = 123.0
    assert store.is_poisoned(key) is False
