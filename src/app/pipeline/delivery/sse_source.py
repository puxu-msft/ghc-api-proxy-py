"""Parsing an upstream SSE byte stream into events.

The space after `data:` is optional in the SSE spec and, when present, is stripped.
Accepting only the spelling with a space silently ignores an upstream that omits it.
This project has already been bitten by that once.

Multiple `data:` lines in one frame join with a newline, as the spec requires.

Line endings are CRLF, LF or a bare CR — the spec allows all three, and a frame ends at the first blank line. Frame *splitting* did not handle that: it looked for `b"\n\n"`, which a CRLF stream never contains, so two well-formed CRLF frames arrived as one. Measured 2026-08-30 — `event: a\r\ndata: 1\r\n\r\nevent: b\r\ndata: 2\r\n\r\n` yielded a single event whose `event` was `b` and whose data was `1\ndata: 2` joined into one string. Not a merge that a reader would notice: the first event's name was simply gone.

Splitting a frame into lines was wrong in the opposite direction, and this docstring used to assert the opposite: *"`parse_frame` has always handled that, because `splitlines()` does."* It handles those three **and more**, and the more is what hurt. See `_LINE_ENDING`.
"""

import codecs
import re
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any, cast

import orjson

# Two consecutive line endings, in any of the three spellings the spec allows and in any combination — `\r\n\r\n`, `\n\n`, `\r\r`, and the mixed forms.
#
# **The atomic group is load-bearing.** Written as `(?:\r\n|\r|\n){2}` the engine backtracks: given `event: a\r\ndata: 1`, it tries `\r\n` for the first ending, fails to find a second at `d`, then retries the first as a bare `\r` and matches the `\n` as the second — splitting a single CRLF into two endings and ending the frame in the middle of one line break. Measured 2026-08-30: that spelling cut `event: a\r\ndata: 1\r\n\r\n` into two frames and lost both event names. `(?>...)` forbids the retry, so a `\r\n` once matched stays one ending.
_FRAME_SEPARATOR = re.compile(rb"(?>\r\n|\r|\n)(?>\r\n|\r|\n)")

# One line ending inside a frame — the same three spellings, and **only** those three.
#
# `str.splitlines()`, which this used to call, breaks on a strict superset: it adds U+000B, U+000C, U+001C through U+001E, U+0085, U+2028 and U+2029. A line ending SSE does not recognise does not merely split a line — it **truncates the payload**, because the remainder has no colon and `parse_frame` skips it. Measured 2026-08-31 on `data: {"delta":"a<CH>b"}`: with U+2028, U+2029, U+0085, VT or FF in place of `<CH>`, the resulting data was `{"delta":"a` — content gone, and no longer parseable JSON.
#
# How much of that is reachable, stated separately from the mechanism: VT and FF must be escaped inside a JSON string and cannot appear raw, so they are unreachable through this upstream. U+2028, U+2029 and U+0085 **are** legal raw inside a JSON string, and whether they arrive depends on upstream's encoder — that is unmeasured. The mechanism is proven; the occurrence is not. Enough to fix, not enough to claim data is being lost in production today.
#
# No atomic group needed here, unlike `_FRAME_SEPARATOR`: there is no second ending to sequence against, so `re.split` matches `\r\n` at a CRLF and never has cause to retry it as a bare `\r`.
_LINE_ENDING = re.compile(r"\r\n|\r|\n")


@dataclass(frozen=True, slots=True)
class SseEvent:
    event: str
    data: str

    def json(self) -> dict[str, Any]:
        """Decode the payload, or return an empty mapping when it is not an object."""
        try:
            loaded: object = orjson.loads(self.data)
        except orjson.JSONDecodeError:
            return {}
        if not isinstance(loaded, dict):
            return {}
        return cast(dict[str, Any], loaded)


@dataclass(frozen=True, slots=True)
class RawSseFrame:
    """One byte-exact SSE frame and its half-open attempt offsets."""

    raw: bytes
    body_end: int
    start: int
    end: int
    ordinal: int
    terminated: bool

    @property
    def body(self) -> memoryview:
        return memoryview(self.raw)[: self.body_end]


@dataclass(frozen=True, slots=True)
class RawFrameFeed:
    """Frames accepted from one chunk and the accepted chunk prefix length."""

    frames: tuple[RawSseFrame, ...]
    consumed: int
    overflowed: bool


class RawSseFrameDecoder:
    """Incrementally split SSE without copying an unbounded transport chunk."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._frame_start = 0
        self._ordinal = 0

    @property
    def held_bytes(self) -> int:
        return len(self._buffer)

    def feed_bounded(
        self,
        chunk: bytes,
        *,
        remaining_capacity: int | None,
    ) -> RawFrameFeed:
        if remaining_capacity is not None and remaining_capacity < 0:
            raise ValueError("remaining_capacity must be non-negative or None")
        view = memoryview(chunk)
        frames: list[RawSseFrame] = []
        cursor = 0
        capacity = remaining_capacity
        while cursor < len(view):
            separator = self._find_separator(view, cursor)
            if separator is None:
                required = len(view) - cursor
                if capacity is not None and required > capacity:
                    self._buffer.clear()
                    return RawFrameFeed(frames=tuple(frames), consumed=cursor, overflowed=True)
                self._buffer.extend(view[cursor:])
                cursor = len(view)
                if capacity is not None:
                    capacity -= required
                break

            body_end, chunk_end = separator
            required = chunk_end - cursor
            if capacity is not None and required > capacity:
                self._buffer.clear()
                return RawFrameFeed(frames=tuple(frames), consumed=cursor, overflowed=True)
            self._buffer.extend(view[cursor:chunk_end])
            raw = bytes(self._buffer)
            frame = RawSseFrame(
                raw=raw,
                body_end=body_end,
                start=self._frame_start,
                end=self._frame_start + len(raw),
                ordinal=self._ordinal,
                terminated=True,
            )
            frames.append(frame)
            self._frame_start = frame.end
            self._ordinal += 1
            self._buffer.clear()
            cursor = chunk_end
            if capacity is not None:
                capacity -= required
        return RawFrameFeed(frames=tuple(frames), consumed=cursor, overflowed=False)

    def finish(self) -> RawSseFrame | None:
        if not self._buffer:
            return None
        raw = bytes(self._buffer)
        separator = _FRAME_SEPARATOR.search(raw)
        terminated = separator is not None
        body_end = separator.start() if separator is not None else len(raw)
        self._buffer.clear()
        frame = RawSseFrame(
            raw=raw,
            body_end=body_end,
            start=self._frame_start,
            end=self._frame_start + len(raw),
            ordinal=self._ordinal,
            terminated=terminated,
        )
        self._frame_start = frame.end
        self._ordinal += 1
        return frame

    def _find_separator(
        self,
        view: memoryview,
        cursor: int,
    ) -> tuple[int, int] | None:
        """Return `(body_end_in_frame, end_in_chunk)` for the earliest separator."""
        prefix_length = min(len(self._buffer), 3)
        bridge = bytes(self._buffer[-prefix_length:]) + bytes(view[cursor : cursor + 3])
        bridge_match = _FRAME_SEPARATOR.search(bridge)
        cross: tuple[int, int] | None = None
        if bridge_match is not None and bridge_match.start() < prefix_length:
            if bridge_match.end() > prefix_length:
                base = len(self._buffer) - prefix_length
                cross = (
                    base + bridge_match.start(),
                    cursor + bridge_match.end() - prefix_length,
                )
            elif bridge_match.end() == prefix_length and cursor < len(view):
                cross = (
                    len(self._buffer) - prefix_length + bridge_match.start(),
                    cursor,
                )

        chunk_match = _FRAME_SEPARATOR.search(view, cursor)
        within: tuple[int, int] | None = None
        if chunk_match is not None:
            within = (
                len(self._buffer) + chunk_match.start() - cursor,
                chunk_match.end(),
            )
        candidate = within
        if cross is not None and (within is None or cross[0] <= within[0]):
            candidate = cross
        if candidate is None:
            return None
        if candidate[1] == len(view) and view[candidate[1] - 1] == 0x0D:
            return None
        return candidate


def parse_frame(raw: bytes | bytearray | memoryview) -> SseEvent | None:
    """Turn one frame into an event, or None when it carries no data."""
    event = ""
    data_lines: list[str] = []
    for line in _LINE_ENDING.split(codecs.decode(raw, "utf-8", errors="replace")):
        if line.startswith(":"):
            continue  # comment, including the keep-alive kind
        name, separator, value = line.partition(":")
        if not separator:
            continue
        if value.startswith(" "):
            value = value[1:]
        if name == "event":
            event = value
        elif name == "data":
            data_lines.append(value)
    if not data_lines:
        return None
    return SseEvent(event=event, data="\n".join(data_lines))


def iter_frames(buffer: bytearray) -> Iterator[bytes]:
    """Take every complete frame out of the buffer, leaving any partial tail behind.

    Searching from the start each time rather than tracking a position: a frame is consumed as it is yielded, so the next search always begins at what is now the start.
    """
    while True:
        found = _FRAME_SEPARATOR.search(buffer)
        if found is None:
            return
        frame = bytes(buffer[: found.start()])
        del buffer[: found.end()]
        yield frame


def encode_frame(event: str, data: str) -> bytes:
    """One SSE frame carrying an event name and a payload, with the payload's own newlines preserved.

    **Each line of `data` gets its own `data:` field**, which is what the spec requires and what makes the payload survive the client's parser. Writing it as a single `data:` line puts the second line on the wire as a bare line, which is not a field at all — the reader sees a line with no colon, skips it, and the payload silently loses everything after the first newline. Measured 2026-08-30 on `_report_failure`, which did exactly that.

    Not `SseFrame`, which takes a mapping and serialises it: this exists for payloads that must go back out as the text they arrived as, where a round trip through a JSON encoder would keep the fields and not the bytes.

    An empty `data` still writes one empty `data:` field, because an event with no `data:` at all is dropped by `parse_frame` — an empty payload and an absent one are different, and only the first is representable.
    """
    lines = [f"event: {event}"] if event else []
    lines.extend(f"data: {line}" for line in data.split("\n"))
    return ("\n".join(lines) + "\n\n").encode()


async def read_events(chunks: AsyncIterator[bytes]) -> AsyncIterator[SseEvent]:
    """Read events off a chunked byte stream.

    Chunk boundaries are arbitrary, so a frame split across two reads must still parse.

    Closing this closes the byte stream under it. A bare `async for` does not: closed early, GeneratorExit unwinds past the loop and leaves the source suspended, to be closed whenever the collector happens to reach it. That is the difference between an upstream HTTP response released at the moment the client goes away and one released a few ticks later — or not at all, once anything holds a reference to the frame.
    """
    decoder = RawSseFrameDecoder()
    close = getattr(chunks, "aclose", None)
    try:
        async for chunk in chunks:
            feed = decoder.feed_bounded(chunk, remaining_capacity=None)
            for frame in feed.frames:
                event = parse_frame(frame.body)
                if event is not None:
                    yield event
        remainder = decoder.finish()
        if remainder is not None:
            event = parse_frame(remainder.body)
            if event is not None:
                yield event
    finally:
        if close is not None:
            await close()
