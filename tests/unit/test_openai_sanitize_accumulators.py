from app.openai.responses_stream_accumulator import ResponsesStreamAccumulator
from app.openai.sanitize import sanitize_chat_messages
from app.openai.stream_accumulator import ChatStreamAccumulator
from app.streaming.translator import translate_chat_event_to_responses


def test_openai_sanitize_removes_orphan_tool_messages_and_calls() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "keep",
            "tool_calls": [
                {"id": "paired", "type": "function", "function": {"name": "A", "arguments": "{}"}},
                {"id": "orphan", "type": "function", "function": {"name": "B", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "paired", "content": "ok"},
        {"role": "tool", "tool_call_id": "missing", "content": "drop"},
    ]

    result = sanitize_chat_messages(messages)

    assert len(result) == 2
    assert [call["id"] for call in result[0]["tool_calls"]] == ["paired"]
    assert result[1]["tool_call_id"] == "paired"


def test_chat_stream_accumulator_collects_text_finish_and_usage() -> None:
    accumulator = ChatStreamAccumulator()
    accumulator.process(
        {
            "id": "chat_1",
            "model": "gpt-test",
            "choices": [{"index": 0, "delta": {"content": "hel"}}],
        }
    )
    accumulator.process(
        {
            "choices": [{"index": 0, "delta": {"content": "lo"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        }
    )

    snapshot = accumulator.snapshot()
    assert snapshot["content"] == "hello"
    assert snapshot["finish_reason"] == "stop"
    assert snapshot["usage"]["completion_tokens"] == 2


def test_responses_stream_accumulator_tracks_terminal_response_and_usage() -> None:
    accumulator = ResponsesStreamAccumulator()
    accumulator.process({"type": "response.output_text.delta", "delta": "hello"})
    accumulator.process(
        {
            "type": "response.completed",
            "response": {"id": "resp_1", "usage": {"output_tokens": 3}},
        }
    )

    snapshot = accumulator.snapshot()
    assert snapshot["output_text"] == "hello"
    assert snapshot["response"]["id"] == "resp_1"
    assert snapshot["usage"]["output_tokens"] == 3


def test_streaming_translator_preserves_source_event() -> None:
    event = {
        "id": "chat_1",
        "future": True,
        "choices": [{"index": 0, "delta": {"content": "hi"}}],
    }

    translated = translate_chat_event_to_responses(event)

    assert translated is not None
    assert translated["delta"] == "hi"
    assert translated["source"]["future"] is True
