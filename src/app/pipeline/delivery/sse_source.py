"""Parsing an upstream SSE byte stream into events.

The space after `data:` is optional in the SSE spec and, when present, is stripped.
Accepting only the spelling with a space silently ignores an upstream that omits it.
This project has already been bitten by that once.

Multiple `data:` lines in one frame join with a newline, as the spec requires.

Line endings are CRLF, LF or a bare CR — the spec allows all three, and a frame ends at the first blank line. `parse_frame` has always handled that, because `splitlines()` does. Frame *splitting* did not: it looked for `b"\n\n"`, which a CRLF stream never contains, so two well-formed CRLF frames arrived as one. Measured 2026-08-30 — `event: a\r\ndata: 1\r\n\r\nevent: b\r\ndata: 2\r\n\r\n` yielded a single event whose `event` was `b` and whose data was `1\ndata: 2` joined into one string. Not a merge that a reader would notice: the first event's name was simply gone.
"""

import re
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any, cast

import orjson

# Two consecutive line endings, in any of the three spellings the spec allows and in any combination — `\r\n\r\n`, `\n\n`, `\r\r`, and the mixed forms.
#
# **The atomic group is load-bearing.** Written as `(?:\r\n|\r|\n){2}` the engine backtracks: given `event: a\r\ndata: 1`, it tries `\r\n` for the first ending, fails to find a second at `d`, then retries the first as a bare `\r` and matches the `\n` as the second — splitting a single CRLF into two endings and ending the frame in the middle of one line break. Measured 2026-08-30: that spelling cut `event: a\r\ndata: 1\r\n\r\n` into two frames and lost both event names. `(?>...)` forbids the retry, so a `\r\n` once matched stays one ending.
_FRAME_SEPARATOR = re.compile(rb"(?>\r\n|\r|\n)(?>\r\n|\r|\n)")


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


def parse_frame(raw: bytes) -> SseEvent | None:
    """Turn one frame into an event, or None when it carries no data."""
    event = ""
    data_lines: list[str] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
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
    buffer = bytearray()
    close = getattr(chunks, "aclose", None)
    try:
        async for chunk in chunks:
            buffer.extend(chunk)
            for frame in iter_frames(buffer):
                event = parse_frame(frame)
                if event is not None:
                    yield event
        if buffer.strip():
            event = parse_frame(bytes(buffer))
            if event is not None:
                yield event
    finally:
        if close is not None:
            await close()
