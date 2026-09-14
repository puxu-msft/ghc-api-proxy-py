import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.pipeline.delivery import BlockBuffer
from app.pipeline.delivery.blocks import CompletedBlock
from app.pipeline.delivery.formats.anthropic_messages import AnthropicFramer
from app.pipeline.delivery.formats.commandcode import CommandCodeAssembler
from app.pipeline.delivery.formats.openai_chat_completions import ChatCompletionsFramer
from app.pipeline.delivery.formats.openai_responses import ResponsesFramer
from app.pipeline.delivery.sse_source import SseEvent, read_ndjson_events
from app.pipeline.delivery.stream import StreamSettings, UpstreamSource, stream_delivery


def test_commandcode_assembler_closes_reasoning_text_and_tool_blocks() -> None:
    assembler = CommandCodeAssembler()

    completed: list[CompletedBlock] = []
    for event in (
        SseEvent("reasoning-delta", json.dumps({"type": "reasoning-delta", "text": "think"})),
        SseEvent("text-delta", json.dumps({"type": "text-delta", "text": "answer"})),
        SseEvent(
            "tool-call",
            json.dumps(
                {
                    "type": "tool-call",
                    "toolCallId": "call_1",
                    "toolName": "weather",
                    "input": {"city": "Seattle"},
                }
            ),
        ),
    ):
        completed.extend(assembler.push(event))
    completed.extend(
        assembler.push(
            SseEvent(
                "finish",
                json.dumps(
                    {
                        "type": "finish",
                        "finishReason": "tool-calls",
                        "totalUsage": {
                            "inputTokens": 10,
                            "outputTokens": 4,
                            "cachedInputTokens": 2,
                        },
                    }
                ),
            )
        )
    )

    assert [block.kind for block in completed] == ["thinking", "text", "tool_use"]
    assert completed[-1].payload["input"] == {"city": "Seattle"}
    assert assembler.terminal.seen is True
    assert assembler.terminal.stop_reason == "tool_use"
    assert assembler.terminal.usage["cache_read_input_tokens"] == 2


def test_commandcode_assembler_delivers_explicit_end_events() -> None:
    assembler = CommandCodeAssembler()
    completed: list[CompletedBlock] = []

    events: tuple[tuple[str, dict[str, Any]], ...] = (
        ("text-start", {}),
        ("text-delta", {"text": "answer"}),
        ("text-end", {}),
        ("reasoning-start", {}),
        ("reasoning-delta", {"text": "think"}),
        ("reasoning-end", {}),
        ("tool-input-start", {"toolCallId": "call_1", "toolName": "weather"}),
        ("tool-input-delta", {"input": '{"city":"Seattle"}'}),
        ("tool-input-end", {}),
    )
    for event in events:
        kind, data = event
        completed.extend(assembler.push(SseEvent(kind, json.dumps({"type": kind, **data}))))

    assert [block.kind for block in completed] == ["text", "thinking", "tool_use"]
    assert completed[-1].payload["input"] == {"city": "Seattle"}
    assert assembler.cut_mid_block is False


def test_commandcode_assembler_marks_malformed_tool_input_and_reuses_fallback_id() -> None:
    assembler = CommandCodeAssembler()
    completed: list[CompletedBlock] = []

    completed.extend(
        assembler.push(
            SseEvent(
                "tool-input-start",
                json.dumps(
                    {
                        "type": "tool-input-start",
                        "toolCallId": None,
                        "toolName": "weather",
                    }
                ),
            )
        )
    )
    completed.extend(
        assembler.push(
            SseEvent(
                "tool-input-delta",
                json.dumps({"type": "tool-input-delta", "input": '{"city":'}),
            )
        )
    )
    completed.extend(
        assembler.push(
            SseEvent(
                "tool-input-end",
                json.dumps({"type": "tool-input-end"}),
            )
        )
    )

    assert completed[0].payload["id"] == "call_0"
    assert completed[0].payload["input"] == {"__raw": '{"city":'}


@pytest.mark.parametrize(
    ("events", "expected_kind"),
    [
        (
            (("text-delta", {"text": "answer"}),),
            "text",
        ),
        (
            (("reasoning-delta", {"text": "think"}),),
            "thinking",
        ),
        (
            (
                ("tool-input-start", {"toolCallId": "call_1", "toolName": "weather"}),
                ("tool-input-delta", {"input": '{"city":"Seattle"}'}),
            ),
            "tool_use",
        ),
    ],
)
def test_commandcode_finish_flushes_open_drafts(
    events: tuple[tuple[str, dict[str, Any]], ...],
    expected_kind: str,
) -> None:
    assembler = CommandCodeAssembler()
    completed: list[CompletedBlock] = []

    for kind, data in events:
        completed.extend(assembler.push(SseEvent(kind, json.dumps({"type": kind, **data}))))
    completed.extend(
        assembler.push(
            SseEvent(
                "finish",
                json.dumps(
                    {
                        "type": "finish",
                        "finishReason": "stop",
                        "totalUsage": {"inputTokens": 1, "outputTokens": 1},
                    }
                ),
            )
        )
    )

    assert [block.kind for block in completed] == [expected_kind]
    assert assembler.cut_mid_block is False
    assert assembler.failure is None


def test_chat_framer_writes_translated_commandcode_blocks_as_chat_sse() -> None:
    frame = ChatCompletionsFramer(message_id="chatcmpl_1", model="m").block(
        CompletedBlock(index=0, kind="text", payload={"type": "text", "text": "hello"})
    )[0]

    body = json.loads(frame.removeprefix(b"data: ").strip())
    assert body["id"] == "chatcmpl_1"
    assert body["choices"][0]["delta"] == {
        "role": "assistant",
        "content": "hello",
    }


def test_commandcode_eof_drops_unfinished_drafts_and_keeps_cut_mid_block() -> None:
    assembler = CommandCodeAssembler()

    assembler.push(
        SseEvent("text-delta", json.dumps({"type": "text-delta", "text": "partial"}))
    )

    assert assembler.close() == ()
    assert assembler.cut_mid_block is True
    assert assembler.terminal.blocks == 0


def test_commandcode_empty_finish_is_an_error_not_an_empty_success() -> None:
    assembler = CommandCodeAssembler()

    assert (
        assembler.push(
            SseEvent(
                "finish",
                json.dumps(
                    {
                        "type": "finish",
                        "finishReason": "stop",
                        "totalUsage": {"inputTokens": 1, "outputTokens": 0},
                    }
                ),
            )
        )
        == ()
    )

    assert assembler.terminal.seen is True
    assert assembler.failure is not None
    assert assembler.failure.info.code == "commandcode_empty_output"


def test_commandcode_finish_distinguishes_missing_and_zero_usage() -> None:
    for usage, code in [
        (None, "commandcode_missing_usage"),
        ({"inputTokens": 1, "outputTokens": 0}, "commandcode_zero_output"),
    ]:
        assembler = CommandCodeAssembler()
        assembler.push(
            SseEvent(
                "text-delta",
                json.dumps({"type": "text-delta", "text": "answer"}),
            )
        )
        assembler.push(
            SseEvent(
                "text-end",
                json.dumps({"type": "text-end"}),
            )
        )
        payload: dict[str, Any] = {"type": "finish", "finishReason": "stop"}
        if usage is not None:
            payload["totalUsage"] = usage
        assembler.push(SseEvent("finish", json.dumps(payload)))

        assert assembler.failure is not None
        assert assembler.failure.info.code == code


def test_commandcode_terminal_usage_is_responses_shaped() -> None:
    assembler = CommandCodeAssembler()

    assembler.push(
        SseEvent("text-delta", json.dumps({"type": "text-delta", "text": "answer"}))
    )
    assembler.push(
        SseEvent(
            "finish",
            json.dumps(
                {
                    "type": "finish",
                    "finishReason": "stop",
                    "totalUsage": {
                        "inputTokens": 10,
                        "outputTokens": 2,
                        "cachedInputTokens": 4,
                    },
                }
            ),
        )
    )

    assert assembler.terminal.upstream_usage == {
        "input_tokens": 10,
        "input_tokens_details": {"cached_tokens": 4, "cache_write_tokens": 0},
        "output_tokens": 2,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": 12,
    }
    terminal_frame = ResponsesFramer(response_id="resp_1", model="m").terminal(
        assembler.terminal
    )[0]
    terminal_body = json.loads(terminal_frame.decode().split("data: ", 1)[1])
    assert terminal_body["response"]["usage"] == assembler.terminal.upstream_usage


@pytest.mark.asyncio
async def test_commandcode_empty_finish_delivers_an_error_frame() -> None:
    async def upstream_bytes() -> AsyncIterator[bytes]:
        yield b'{"type":"finish","finishReason":"stop"}\n'

    upstream = UpstreamSource(upstream_bytes())
    body = [
        chunk
        async for chunk in stream_delivery(
            upstream,
            CommandCodeAssembler(),
            upstream=upstream,
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0),
            framer=AnthropicFramer(message_id="msg_1", model="m"),
            event_reader=read_ndjson_events,
        )
    ]

    assert body
    assert b"commandcode_empty_output" in b"".join(body)


@pytest.mark.asyncio
async def test_commandcode_empty_eof_delivers_an_error_frame() -> None:
    async def upstream_bytes() -> AsyncIterator[bytes]:
        if False:
            yield b""

    upstream = UpstreamSource(upstream_bytes())
    body = [
        chunk
        async for chunk in stream_delivery(
            upstream,
            CommandCodeAssembler(),
            upstream=upstream,
            buffer=BlockBuffer(policy="block"),
            settings=StreamSettings(sse_ping_interval=0),
            framer=AnthropicFramer(message_id="msg_1", model="m"),
            event_reader=read_ndjson_events,
        )
    ]

    assert body
    assert b"commandcode_incomplete_stream" in b"".join(body)
