from app.transform.system_prompt import SystemPromptRules, apply_system_prompt_rules
from app.transform.translator import anthropic_to_openai, openai_to_anthropic


def test_openai_to_anthropic_extracts_system_and_preserves_unknown_fields() -> None:
    payload = {
        "model": "claude-test",
        "messages": [
            {"role": "system", "content": "be useful", "future_system": True},
            {"role": "user", "content": "hello", "future_message": {"x": 1}},
        ],
        "future_request": None,
    }

    translated = openai_to_anthropic(payload)

    assert translated["system"] == "be useful"
    assert translated["messages"] == [
        {"role": "user", "content": "hello", "future_message": {"x": 1}}
    ]
    assert "future_request" in translated


def test_openai_tool_call_maps_to_anthropic_blocks() -> None:
    payload = {
        "model": "claude-test",
        "messages": [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "Read", "arguments": '{"path":"x"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "result"},
        ],
    }

    translated = openai_to_anthropic(payload)

    assert translated["messages"][0]["content"][0] == {
        "type": "tool_use",
        "id": "call_1",
        "name": "Read",
        "input": {"path": "x"},
    }
    assert translated["messages"][1]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "call_1",
        "content": "result",
    }


def test_anthropic_to_openai_maps_text_and_tool_blocks() -> None:
    payload = {
        "model": "claude-test",
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "tool_use", "id": "tool_1", "name": "Read", "input": {"path": "x"}},
                ],
            }
        ],
    }

    translated = anthropic_to_openai(payload)

    assert translated["messages"][0]["content"] == "hello"
    assert translated["messages"][0]["tool_calls"][0]["function"]["name"] == "Read"


def test_system_prompt_rules_apply_replace_prepend_append_without_mutating_input() -> None:
    messages = [{"role": "system", "content": "old rule"}, {"role": "user", "content": "hi"}]
    rules = SystemPromptRules(
        prepend=("prefix",),
        append=("suffix",),
        replacements=(("old", "new"),),
    )

    result = apply_system_prompt_rules(messages, rules)

    assert result[0]["content"] == "prefix\nnew rule\nsuffix"
    assert messages[0]["content"] == "old rule"


def test_anthropic_list_system_and_tool_result_are_preserved() -> None:
    payload = {
        "model": "claude-test",
        "system": [
            {"type": "text", "text": "first", "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "second"},
        ],
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool_1",
                        "content": "result",
                        "future": True,
                    }
                ],
            }
        ],
    }

    translated = anthropic_to_openai(payload)

    assert translated["messages"][0]["content"] == "first\nsecond"
    assert translated["messages"][1] == {
        "role": "tool",
        "tool_call_id": "tool_1",
        "content": "result",
        "future": True,
    }


def test_openai_tool_message_extra_fields_are_preserved() -> None:
    payload = {
        "messages": [
            {
                "role": "tool",
                "tool_call_id": "tool_1",
                "content": "result",
                "future": {"keep": True},
            }
        ]
    }

    translated = openai_to_anthropic(payload)

    assert translated["messages"][0]["future"] == {"keep": True}
