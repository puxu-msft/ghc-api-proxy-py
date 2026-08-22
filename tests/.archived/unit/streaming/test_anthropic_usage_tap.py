from app.streaming.anthropic_usage import AnthropicSSEUsageTap


def test_usage_tap_handles_split_frames_without_changing_chunks() -> None:
    chunks = [
        b'event: message_start\ndata: {"type":"message_start",'
        b'"message":{"usage":{"input_tokens":10,',
        b'"cache_read_input_tokens":4}}}\n\n',
        b'event: message_delta\ndata: {"type":"message_delta",'
        b'"usage":{"output_tokens":3}}\n\n',
    ]
    tap = AnthropicSSEUsageTap()
    forwarded: list[bytes] = []

    for chunk in chunks:
        tap.feed(chunk)
        forwarded.append(chunk)

    assert forwarded == chunks
    assert tap.usage == {
        "input_tokens": 10,
        "cache_read_input_tokens": 4,
        "output_tokens": 3,
    }


def test_usage_tap_ignores_malformed_data() -> None:
    tap = AnthropicSSEUsageTap()

    tap.feed(b"data: {broken}\n\ndata: [DONE]\n\n")

    assert tap.usage == {}
