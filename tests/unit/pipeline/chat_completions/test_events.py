import pytest

from app.pipeline.chat_completions.events import ChatEventKind, ChatEventReader
from app.pipeline.delivery.sse_source import RawSseFrame, RawSseFrameDecoder, parse_frame
from app.pipeline.response_observation import JsonAvailability
from app.pipeline.retry import RetryReason


def _decode(*chunks: bytes) -> list[RawSseFrame]:
    decoder = RawSseFrameDecoder()
    frames = list[RawSseFrame]()
    for chunk in chunks:
        feed = decoder.feed_bounded(chunk, remaining_capacity=None)
        assert feed.consumed == len(chunk)
        assert feed.overflowed is False
        frames.extend(feed.frames)
    remainder = decoder.finish()
    if remainder is not None:
        frames.append(remainder)
    return frames


def test_raw_frames_preserve_original_bytes_separators_and_offsets() -> None:
    raw = b"event: a\r\ndata: 1\r\n\r\ndata: 2\n\nevent: c\rdata: 3\r\r"

    frames = _decode(raw[:11], raw[11:31], raw[31:])

    expected = [
        b"event: a\r\ndata: 1\r\n\r\n",
        b"data: 2\n\n",
        b"event: c\rdata: 3\r\r",
    ]
    assert [frame.raw for frame in frames] == expected
    assert [frame.body.tobytes() for frame in frames] == [
        b"event: a\r\ndata: 1",
        b"data: 2",
        b"event: c\rdata: 3",
    ]
    assert [(frame.start, frame.end) for frame in frames] == [(0, 21), (21, 30), (30, 48)]
    assert [frame.ordinal for frame in frames] == [0, 1, 2]
    assert all(frame.terminated for frame in frames)
    assert all(frame.body.obj is frame.raw for frame in frames)
    assert b"".join(frame.raw for frame in frames) == raw


@pytest.mark.parametrize(
    "separator",
    [
        b"\r\n\r\n",
        b"\r\n\r",
        b"\r\n\n",
        b"\r\r\n",
        b"\r\r",
        b"\n\r\n",
        b"\n\r",
        b"\n\n",
    ],
)
def test_every_byte_split_preserves_an_ambiguous_cr_separator(separator: bytes) -> None:
    raw = b"data: [DONE]" + separator
    for split in range(len(raw) + 1):
        frames = _decode(raw[:split], raw[split:])
        assert len(frames) == 1, (separator, split)
        assert frames[0].raw == raw, (separator, split)
        assert frames[0].body.tobytes() == b"data: [DONE]", (separator, split)
        assert (frames[0].start, frames[0].end, frames[0].ordinal) == (
            0,
            len(raw),
            0,
        )
        assert frames[0].terminated is True


def test_ambiguous_done_separator_must_fit_through_the_delayed_lf() -> None:
    prefix = b"data: [DONE]\r\n\r"
    decoder = RawSseFrameDecoder()

    first = decoder.feed_bounded(prefix, remaining_capacity=len(prefix))
    second = decoder.feed_bounded(b"\n", remaining_capacity=0)

    assert first.frames == ()
    assert first.consumed == len(prefix)
    assert decoder.held_bytes == 0
    assert second.frames == ()
    assert second.consumed == 0
    assert second.overflowed is True


def test_finish_returns_one_unterminated_eof_remainder_and_clears_it() -> None:
    raw = b"event: x\ndata: first\ndata: second"
    decoder = RawSseFrameDecoder()

    feed = decoder.feed_bounded(raw, remaining_capacity=len(raw))
    remainder = decoder.finish()

    assert feed.frames == ()
    assert remainder is not None
    assert remainder.raw == raw
    assert remainder.body.tobytes() == raw
    assert remainder.body.obj is remainder.raw
    assert (remainder.start, remainder.end, remainder.ordinal, remainder.terminated) == (
        0,
        len(raw),
        0,
        False,
    )
    assert decoder.held_bytes == 0
    assert decoder.finish() is None
    parsed = parse_frame(remainder.body)
    assert parsed is not None
    assert (parsed.event, parsed.data) == ("x", "first\nsecond")


def test_bounded_feed_accepts_done_then_rejects_the_next_whole_frame() -> None:
    done = b"data: [DONE]\n\n"
    tail = b'data: {"too":"large"}\n\n'
    decoder = RawSseFrameDecoder()

    feed = decoder.feed_bounded(done + tail, remaining_capacity=len(done))

    assert feed.consumed == len(done)
    assert feed.overflowed is True
    assert [frame.raw for frame in feed.frames] == [done]
    assert feed.frames[0].body.obj is feed.frames[0].raw
    assert decoder.held_bytes == 0


def test_bounded_feed_does_not_retain_any_part_of_an_overflowing_frame() -> None:
    decoder = RawSseFrameDecoder()
    first = decoder.feed_bounded(b"data: partial", remaining_capacity=20)
    assert first.consumed == len(b"data: partial")
    assert decoder.held_bytes == len(b"data: partial")

    second = decoder.feed_bounded(b" remainder\n\n", remaining_capacity=2)

    assert second.consumed == 0
    assert second.frames == ()
    assert second.overflowed is True
    assert decoder.held_bytes == 0


def test_error_carrier_precedes_choices_and_classifies_known_transient_values() -> None:
    [frame] = _decode(
        b'data: {"error":{"code":"server_error","type":"server_error"},"choices":[{"index":0}]}\n\n'
    )

    facts = ChatEventReader().read(frame)

    assert facts.kind is ChatEventKind.ERROR
    assert facts.error_values == ("server_error", "server_error")
    assert facts.retry_reason is RetryReason.SERVER_ERROR


@pytest.mark.parametrize(
    "raw",
    [
        b'data: {"type":"error","code":"rate_limit_exceeded"}\n\n',
        b'event: error\ndata: {"type":"error","code":"rate_limited"}\n\n',
    ],
)
def test_flat_error_carriers_are_recognized(raw: bytes) -> None:
    [frame] = _decode(raw)

    facts = ChatEventReader().read(frame)

    assert facts.kind is ChatEventKind.ERROR
    assert facts.error_values == ("rate_limit_exceeded",) or facts.error_values == ("rate_limited",)
    assert facts.retry_reason is RetryReason.SERVER_ERROR


def test_error_event_name_precedes_done_sentinel_text() -> None:
    [frame] = _decode(b"event: error\ndata: [DONE]\n\n")

    facts = ChatEventReader().read(frame)

    assert facts.kind is ChatEventKind.ERROR
    assert facts.retry_reason is None
    assert facts.issue is not None
    assert facts.issue.code == "chat_error_malformed_json"


def test_conflicting_transient_error_classes_do_not_retry() -> None:
    [frame] = _decode(
        b'data: {"error":{"code":"server_error","type":"rate_limit_error"}}\n\n'
    )

    facts = ChatEventReader().read(frame)

    assert facts.kind is ChatEventKind.ERROR
    assert facts.error_values == ("server_error", "rate_limit_error")
    assert facts.retry_reason is None
    assert facts.issue is not None
    assert facts.issue.code == "chat_error_code_conflict"


def test_strict_json_keeps_null_array_malformed_and_empty_object_distinct() -> None:
    null, array, malformed, empty = _decode(
        b"data: null\n\ndata: []\n\ndata: {bad}\n\ndata: {}\n\n"
    )
    reader = ChatEventReader()

    null_facts = reader.read(null)
    array_facts = reader.read(array)
    malformed_facts = reader.read(malformed)
    empty_facts = reader.read(empty)
    assert null_facts.kind is ChatEventKind.UNKNOWN
    assert null_facts.value.availability is JsonAvailability.EXPLICIT_NULL
    assert array_facts.kind is ChatEventKind.UNKNOWN
    assert array_facts.value.availability is JsonAvailability.OBSERVED
    assert malformed_facts.kind is ChatEventKind.UNREADABLE
    assert malformed_facts.value.availability is JsonAvailability.UNREADABLE
    assert empty_facts.kind is ChatEventKind.CHUNK
    assert empty_facts.value.availability is JsonAvailability.OBSERVED


def test_known_error_survives_an_unfreezable_unrelated_number() -> None:
    [frame] = _decode(
        b'event: error\ndata: {"error":{"code":"server_error"},"future":1e400}\n\n'
    )

    facts = ChatEventReader().read(frame)

    assert facts.kind is ChatEventKind.ERROR
    assert facts.error_values == ("server_error",)
    assert facts.retry_reason is RetryReason.SERVER_ERROR
    assert facts.value.availability is JsonAvailability.UNREADABLE
    assert facts.issue is not None
    assert facts.issue.code == "chat_error_value_unreadable"
