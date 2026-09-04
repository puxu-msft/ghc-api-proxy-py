"""The Chat Completions assembler: chunks without block boundaries, assembled into
blocks; drafts flushed at close rather than dropped.
"""

from typing import Any

from app.pipeline.delivery.assembling import ReplyDialect
from app.pipeline.delivery.formats.openai_chat_completions import ChatCompletionsAssembler
from app.pipeline.delivery.sse_source import SseEvent
from app.pipeline.translation_driver.openai_chat_completions import (
    from_chat_completions_response,
)
from app.pipeline.translation_driver.reasoning_carrier import (
    CHAT_REASONING_CONTENT,
    RESPONSES_SUMMARY_TEXT_LAYOUT,
    decode_reasoning_carrier,
)


def chunk(delta: dict[str, Any], finish: str | None = None) -> SseEvent:
    data: dict[str, Any] = {
        "id": "c",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return SseEvent(event="", data=_json(data))


def usage_chunk() -> SseEvent:
    return SseEvent(
        event="",
        data=_json(
            {
                "id": "c",
                "choices": [],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            }
        ),
    )


def done() -> SseEvent:
    return SseEvent(event="", data="[DONE]")


def _json(data: Any) -> str:
    import json

    return json.dumps(data)


def test_text_deltas_assemble_into_one_block() -> None:
    assembler = ChatCompletionsAssembler()

    assert assembler.push(chunk({"content": "he"})) == ()
    blocks = assembler.push(chunk({"content": "llo"}, finish="stop"))

    assert len(blocks) == 1
    assert blocks[0].kind == "text"
    assert blocks[0].payload["text"] == "hello"
    assert assembler.terminal.stop_reason == "end_turn"
    assert assembler.terminal.seen is True


def test_a_finish_reason_closes_every_open_draft() -> None:
    assembler = ChatCompletionsAssembler()
    assembler.push(chunk({"content": "partial"}))

    blocks = assembler.push(chunk({}, finish="length"))

    assert [block.kind for block in blocks] == ["text"]
    assert assembler.terminal.stop_reason == "max_tokens"


def test_tool_call_fragments_assemble_by_index() -> None:
    assembler = ChatCompletionsAssembler()
    assembler.push(
        chunk(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "c1",
                        "function": {"name": "weather", "arguments": '{"city":'},
                    }
                ]
            }
        )
    )

    blocks = assembler.push(
        chunk(
            {
                "tool_calls": [
                    {"index": 0, "function": {"arguments": '"sz"}'}}
                ]
            },
            finish="tool_calls",
        )
    )

    assert len(blocks) == 1
    assert blocks[0].kind == "tool_use"
    assert blocks[0].payload["id"] == "c1"
    assert blocks[0].payload["name"] == "weather"
    assert blocks[0].payload["input"] == {"city": "sz"}
    assert assembler.terminal.stop_reason == "tool_use"
    assert assembler.terminal.tools == ["weather"]


def test_a_second_tool_index_closes_the_first() -> None:
    assembler = ChatCompletionsAssembler()
    assembler.push(
        chunk({"tool_calls": [{"index": 0, "id": "a", "function": {"name": "f", "arguments": "{}"}}]})
    )

    blocks = assembler.push(
        chunk({"tool_calls": [{"index": 1, "id": "b", "function": {"name": "g", "arguments": "{}"}}]})
    )

    assert [block.payload["id"] for block in blocks] == ["a"]
    assert assembler.push(chunk({}, finish="tool_calls"))[0].payload["id"] == "b"
    assert assembler.terminal.tools == ["f", "g"]


def test_reasoning_content_becomes_a_thinking_block_before_the_text() -> None:
    assembler = ChatCompletionsAssembler()
    assembler.push(chunk({"reasoning_content": "thinking..."}))

    thinking = assembler.push(chunk({"content": "answer"}))

    assert [block.kind for block in thinking] == ["thinking"]
    assert thinking[0].payload["type"] == "thinking"
    assert thinking[0].payload["thinking"] == "thinking..."
    carrier = decode_reasoning_carrier(thinking[0].payload["signature"])
    assert {record.type for record in carrier.records} == {
        CHAT_REASONING_CONTENT,
        RESPONSES_SUMMARY_TEXT_LAYOUT,
    }
    assert thinking[0].reasoning is not None
    buffered = from_chat_completions_response(
        {
            "id": "chatcmpl-reasoning",
            "model": "glm-5.2",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "reasoning_content": "thinking...",
                        "content": "answer",
                    },
                }
            ],
        }
    )
    assert thinking[0].reasoning == buffered.blocks[0].reasoning
    final = assembler.push(chunk({}, finish="stop"))
    assert [block.kind for block in final] == ["text"]
    assert assembler.terminal.thinking == ["txt"]


def test_usage_is_converted_to_anthropic_keys() -> None:
    assembler = ChatCompletionsAssembler()
    assembler.push(chunk({"content": "x"}))
    assembler.push(usage_chunk())
    assembler.push(chunk({}, finish="stop"))

    assert assembler.terminal.usage == {"input_tokens": 7, "output_tokens": 3}
    # The original object is kept beside the conversion, as on every leg.
    assert assembler.terminal.upstream_usage is None


def test_cached_usage_is_reported() -> None:
    assembler = ChatCompletionsAssembler()
    data: dict[str, Any] = {
        "id": "c",
        "choices": [],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 1,
            "prompt_tokens_details": {"cached_tokens": 90},
        },
    }

    assembler.push(SseEvent(event="", data=_json(data)))

    assert assembler.terminal.usage["cache_read_input_tokens"] == 90


def test_done_without_finish_marks_seen_and_flushes() -> None:
    assembler = ChatCompletionsAssembler()
    assembler.push(chunk({"content": "cut"}))

    blocks = assembler.push(done())

    assert [block.kind for block in blocks] == ["text"]
    assert assembler.terminal.seen is True
    # Nobody said why the turn ended; the terminal does not claim one.
    assert assembler.terminal.stop_reason == ""


def test_close_flushes_an_open_draft_rather_than_dropping_it() -> None:
    assembler = ChatCompletionsAssembler()
    assembler.push(chunk({"content": "arrived whole"}))
    assert assembler.cut_mid_block is True

    blocks = assembler.close()

    assert [block.payload["text"] for block in blocks] == ["arrived whole"]
    assert assembler.cut_mid_block is False


def test_a_bare_error_object_becomes_a_stream_failure() -> None:
    assembler = ChatCompletionsAssembler()

    assembler.push(SseEvent(event="", data=_json({"error": {"code": "sensitive", "message": "blocked"}})))

    assert assembler.failure is not None
    assert assembler.failure.info.message == "blocked"


def test_the_terminal_is_named_for_the_chat_dialect() -> None:
    assembler = ChatCompletionsAssembler()

    assert assembler.terminal.dialect is ReplyDialect.CHAT_COMPLETIONS
