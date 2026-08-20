"""SSE framing of already-complete blocks.

The assertions here are about the envelope.
Whether a block may go out at all is the buffer's job, tested in test_block_delivery.
"""

from typing import Any

import orjson

from app.pipeline.delivery import CompletedBlock, block_frames, render, terminal_frames


def block(index: int, kind: str = "text", **payload: Any) -> CompletedBlock:
    body: dict[str, Any] = {"type": kind, **payload}
    return CompletedBlock(index=index, kind=kind, payload=body)


def events(chunks: list[bytes]) -> list[str]:
    return [
        line.removeprefix("event: ")
        for chunk in chunks
        for line in chunk.decode().splitlines()
        if line.startswith("event: ")
    ]


def payloads(chunks: list[bytes]) -> list[dict[str, Any]]:
    return [
        orjson.loads(line.removeprefix("data: "))
        for chunk in chunks
        for line in chunk.decode().splitlines()
        if line.startswith("data: ")
    ]


def test_a_block_is_framed_as_a_closed_group() -> None:
    frames = block_frames(block(0, text="hello"))
    assert [frame.event for frame in frames] == [
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
    ]


def test_the_delta_carries_the_whole_finished_text() -> None:
    # One delta with the complete content.
    # The wire format has a delta; the content does not arrive in pieces.
    frames = block_frames(block(0, text="hello world"))
    delta = frames[1].data["delta"]
    assert delta == {"type": "text_delta", "text": "hello world"}


def test_start_frame_does_not_repeat_the_content() -> None:
    frames = block_frames(block(0, text="hello"))
    assert frames[0].data["content_block"]["text"] == ""


def test_thinking_block_uses_its_own_delta_type() -> None:
    frames = block_frames(block(0, kind="thinking", thinking="considering"))
    assert frames[1].data["delta"] == {"type": "thinking_delta", "thinking": "considering"}


def test_tool_use_arguments_ride_in_the_delta_as_json_text() -> None:
    frames = block_frames(block(0, kind="tool_use", name="Read", input={"path": "/tmp/x"}))
    assert frames[0].data["content_block"]["input"] == {}
    delta = frames[1].data["delta"]
    assert delta["type"] == "input_json_delta"
    assert orjson.loads(delta["partial_json"]) == {"path": "/tmp/x"}


def test_unknown_kind_is_framed_without_inventing_a_delta() -> None:
    frames = block_frames(block(0, kind="future_kind"))
    assert [frame.event for frame in frames] == ["content_block_start", "content_block_stop"]


def test_block_index_is_carried_on_every_frame() -> None:
    frames = block_frames(block(3, text="x"))
    assert all(frame.data["index"] == 3 for frame in frames)


def test_a_full_message_is_framed_in_order() -> None:
    chunks = list(
        render(
            [block(0, text="one"), block(1, kind="tool_use", name="Read", input={})],
            message_id="msg_1",
            model="claude-model",
        )
    )
    assert events(chunks) == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]


def test_terminal_closes_only_after_every_block() -> None:
    chunks = list(render([block(0, text="x")], message_id="m", model="model"))
    names = events(chunks)
    assert names.index("content_block_stop") < names.index("message_delta")
    assert names[-1] == "message_stop"


def test_an_empty_message_produces_no_preamble() -> None:
    # A response with no blocks must not emit message_start.
    # The client would read that as a message that began.
    assert list(render([], message_id="m", model="model")) == []


def test_stop_reason_and_usage_reach_the_terminal_frames() -> None:
    frames = terminal_frames(stop_reason="max_tokens", usage={"output_tokens": 12})
    assert frames[0].data["delta"]["stop_reason"] == "max_tokens"
    assert frames[0].data["usage"] == {"output_tokens": 12}


def test_frames_are_encoded_as_valid_sse() -> None:
    chunk = block_frames(block(0, text="hi"))[0].encode()
    text = chunk.decode()
    assert text.startswith("event: content_block_start\ndata: {")
    assert text.endswith("\n\n")


def test_message_start_names_the_model_and_id() -> None:
    chunks = list(render([block(0, text="x")], message_id="msg_7", model="claude-model"))
    first = payloads(chunks)[0]
    assert first["message"]["id"] == "msg_7"
    assert first["message"]["model"] == "claude-model"
    assert first["message"]["content"] == []
