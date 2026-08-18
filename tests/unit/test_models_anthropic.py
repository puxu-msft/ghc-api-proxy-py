from app.models.anthropic import (
    MessagesRequest,
    MessagesResponse,
    MessageStreamEvent,
)


def test_messages_request_preserves_unknown_fields_recursively() -> None:
    request = MessagesRequest.model_validate(
        {
            "model": "claude-test",
            "max_tokens": 100,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "future_block", "future": {"enabled": True}}
                    ],
                    "message_extension": "keep",
                }
            ],
            "request_extension": {"keep": True},
        }
    )

    dumped = request.model_dump(mode="json", exclude_none=True)
    assert dumped["request_extension"] == {"keep": True}
    assert dumped["messages"][0]["message_extension"] == "keep"
    assert dumped["messages"][0]["content"][0]["future"] == {"enabled": True}


def test_messages_response_preserves_unknown_content_block() -> None:
    response = MessagesResponse.model_validate(
        {
            "id": "msg_1",
            "model": "claude-test",
            "content": [{"type": "future", "payload": {"x": 1}}],
            "usage": {"input_tokens": 1, "output_tokens": 2, "future_usage": 3},
        }
    )

    dumped = response.model_dump(mode="json", exclude_none=True)
    assert dumped["content"][0]["payload"] == {"x": 1}
    assert dumped["usage"]["future_usage"] == 3


def test_stream_event_preserves_unknown_delta_fields() -> None:
    event = MessageStreamEvent.model_validate(
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "future_delta", "value": {"nested": True}},
        }
    )

    assert event.model_dump(mode="json")["delta"]["value"] == {"nested": True}
