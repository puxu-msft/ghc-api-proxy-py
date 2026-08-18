from app.anthropic.sanitize.deduplicate_tool_calls import deduplicate_tool_calls
from app.anthropic.sanitize.read_tool_result_tags import strip_read_tool_result_tags
from app.anthropic.sanitize.system_reminders import strip_system_reminders
from app.anthropic.thinking.signature_compat import signature_delta_for_start


def test_system_reminder_stripping() -> None:
    text = "before<system-reminder>secret</system-reminder>after"
    assert strip_system_reminders(text) == "beforeafter"


def test_read_tool_result_tag_stripping_only_targets_read_results() -> None:
    block = {
        "type": "tool_result",
        "tool_name": "Read",
        "content": "file<system-reminder>rule</system-reminder>",
    }
    assert strip_read_tool_result_tags(block)["content"] == "file"


def test_tool_call_dedup_keeps_last_pair() -> None:
    messages = [
    {"role": "user", "content": "keep me"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "a", "name": "Read", "input": {"p": 1}}],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "a", "content": "old"}],
        },
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "b", "name": "Read", "input": {"p": 1}}],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "b", "content": "new"}],
        },
    ]
    result = deduplicate_tool_calls(messages, "input")
    assert len(result) == 3
    assert result[0] == {"role": "user", "content": "keep me"}
    assert result[1]["content"][0]["id"] == "b"


def test_signature_compat_emits_delta_for_inline_signature() -> None:
    start = {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "thinking", "thinking": "", "signature": "sig"},
    }
    delta = signature_delta_for_start(start)
    assert delta == {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "signature_delta", "signature": "sig"},
    }
