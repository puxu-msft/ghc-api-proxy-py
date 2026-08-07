from typing import Any

import pytest
from anthropic.types import Message as SdkMessage
from pydantic import TypeAdapter, ValidationError

from app.anthropic.response_validation import validate_messages_response_wire
from app.models.anthropic import MessagesResponse


def _message(content: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "msg_strict",
        "type": "message",
        "role": "assistant",
        "model": "claude-test",
        "content": content,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


@pytest.mark.parametrize(
    "content",
    [
        [{"type": "text", "text": "ok"}],
        [{"type": "tool_use", "id": "tool_1", "name": "lookup", "input": {}}],
        [{"type": "thinking", "thinking": "why", "signature": "sig"}],
        [{"type": "redacted_thinking", "data": "opaque"}],
        [
            {
                "type": "server_tool_use",
                "id": "server_tool_1",
                "name": "web_search",
                "input": {"query": "weather"},
            }
        ],
        [
            {
                "type": "web_search_tool_result",
                "tool_use_id": "server_tool_1",
                "content": [
                    {
                        "type": "web_search_result",
                        "url": "https://example.test/result",
                        "title": "Example result",
                        "encrypted_content": "opaque",
                    }
                ],
            }
        ],
        [
            {"type": "text", "text": "ok"},
            {"type": "tool_use", "id": "tool_1", "name": "lookup", "input": {}},
            {"type": "thinking", "thinking": "why", "signature": "sig"},
            {"type": "redacted_thinking", "data": "opaque"},
        ],
    ],
    ids=[
        "text",
        "tool-use",
        "thinking",
        "redacted-thinking",
        "server-tool-use",
        "web-search-tool-result",
        "multiple-blocks",
    ],
)
def test_strict_wire_validator_accepts_sdk_messages(
    content: list[dict[str, Any]],
) -> None:
    payload = _message(content)

    validated = validate_messages_response_wire(payload)

    assert validated == payload
    TypeAdapter(SdkMessage).validate_python(validated)
    projected = MessagesResponse.model_validate(validated)
    assert projected.model_dump(mode="json", exclude_none=True)["content"] == content


@pytest.mark.parametrize(
    "payload",
    [
        {key: value for key, value in _message([]).items() if key != "type"},
        {key: value for key, value in _message([]).items() if key != "role"},
        {**_message([]), "type": "response"},
        {**_message([]), "role": "user"},
        _message([{"type": "text"}]),
        _message([{"type": "text", "text": "ok", "id": "mixed"}]),
        _message([{"type": "tool_use", "name": "lookup", "input": {}}]),
        _message([{"type": "tool_use", "id": "tool_1", "input": {}}]),
        _message([{"type": "tool_use", "id": "tool_1", "name": "lookup"}]),
        _message(
            [
                {
                    "type": "tool_use",
                    "id": "tool_1",
                    "name": "lookup",
                    "input": {},
                    "text": "mixed",
                }
            ]
        ),
        _message([{"type": "thinking", "thinking": "why"}]),
        _message([{"type": "future", "payload": {}}]),
        _message(
            [
                {"type": "text", "text": "valid-first"},
                {"type": "text", "text": "invalid-second", "id": "mixed"},
            ]
        ),
    ],
    ids=[
        "missing-type",
        "missing-role",
        "wrong-type",
        "wrong-role",
        "text-missing-text",
        "text-mixed-fields",
        "tool-missing-id",
        "tool-missing-name",
        "tool-missing-input",
        "tool-mixed-fields",
        "thinking-missing-signature",
        "unknown-block",
        "second-block-mixed-fields",
    ],
)
def test_strict_wire_validator_rejects_invalid_messages(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        validate_messages_response_wire(payload)