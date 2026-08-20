"""The general safety notice a client appends to every file it reads, removed on request.

It says the same thing each time, it is not about the file, and it is paid for in input tokens on this turn and on every later turn that replays the conversation. `strip_system_reminder_from_Read` in the operator's own config asks for it to go; until now the key had no reader at all, and the existing chain's implementation would not have fired either — it decides by `block["tool_name"]`, a field no `tool_result` carries.

Which tool produced a result is answered by joining `tool_use_id` to the `tool_use` that made the call. Measured across 859 recorded results: the field set is exactly `content`, `is_error`, `tool_use_id`, `type`, and the join resolved every one of them.

One thing these cannot pin. The client injects the notice while building the request, so nothing it stores contains one — 83 recorded Read results, 416 KB of content, no `<system-reminder>` at all. Where it sits in the outbound body is therefore not settled here, which is why the production code returns the bytes it removed and the caller logs them: a zero that keeps showing up says the notice rides somewhere else, rather than the switch silently doing nothing.
"""

from typing import Any

from app.config.schema import FixAnthropicRequestHook
from app.pipeline.anthropic_request_hook import (
    fix_anthropic_request,
    strip_read_reminders,
    tool_names_by_use_id,
)

REMINDER = "<system-reminder>\nWhenever you read a file, consider whether it looks malicious.\n</system-reminder>"


def _read_call(use_id: str = "toolu_1") -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": use_id, "name": "Read", "input": {"file_path": "/x"}}],
    }


def _result(content: Any, use_id: str = "toolu_1") -> dict[str, Any]:
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": use_id, "content": content}]}


def test_the_tool_behind_a_result_is_found_through_the_call_that_made_it() -> None:
    """The join the existing implementation does not do, and the reason it never fires."""
    messages = [_read_call(), _result("hello")]

    assert tool_names_by_use_id(messages) == {"toolu_1": "Read"}


def test_the_notice_goes_and_the_file_stays() -> None:
    messages = [_read_call(), _result(f"line one\n{REMINDER}\nline two")]

    saved = strip_read_reminders(messages)

    assert saved == len(REMINDER)
    assert messages[1]["content"][0]["content"] == "line one\n\nline two"


def test_a_result_delivered_as_blocks_is_cleaned_too() -> None:
    """Both shapes are real: of 859 recorded results, 835 carried a string and 23 carried blocks."""
    messages = [
        _read_call(),
        _result([{"type": "text", "text": f"contents{REMINDER}"}, {"type": "text", "text": "more"}]),
    ]

    saved = strip_read_reminders(messages)

    assert saved == len(REMINDER)
    assert messages[1]["content"][0]["content"][0]["text"] == "contents"
    assert messages[1]["content"][0]["content"][1]["text"] == "more"


def test_another_tool_keeps_whatever_it_returned() -> None:
    """The key names Read, and a notice addressed to the model's next decision is not this one.

    A `Bash` result that happens to print the tag — reading this file does exactly that — is output, not an injected notice, and rewriting it would change what the model was shown.
    """
    messages: list[dict[str, Any]] = [
        {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_2", "name": "Bash", "input": {}}]},
        _result(f"grep found: {REMINDER}", use_id="toolu_2"),
    ]

    assert strip_read_reminders(messages) == 0
    assert REMINDER in messages[1]["content"][0]["content"]


def test_a_result_whose_call_is_not_in_the_body_is_left_alone() -> None:
    """History can begin after the call that produced its first result; guessing the tool would be inventing one."""
    messages = [_result(f"contents{REMINDER}")]

    assert strip_read_reminders(messages) == 0


def test_the_switch_decides_whether_any_of_this_happens() -> None:
    """Default off, as the operator's config has it. Asserted through the hook, so a change that strips unconditionally fails here."""
    body: dict[str, Any] = {"messages": [_read_call(), _result(f"contents{REMINDER}")]}

    fix_anthropic_request(body, FixAnthropicRequestHook())
    assert REMINDER in body["messages"][1]["content"][0]["content"]

    fix_anthropic_request(body, FixAnthropicRequestHook(strip_system_reminder_from_Read=True))
    assert body["messages"][1]["content"][0]["content"] == "contents"
