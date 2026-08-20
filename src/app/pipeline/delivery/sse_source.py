"""Parsing an upstream SSE byte stream into events.

The space after `data:` is optional in the SSE spec and, when present, is stripped.
Accepting only the spelling with a space silently ignores an upstream that omits it.
This project has already been bitten by that once.

Multiple `data:` lines in one frame join with a newline, as the spec requires.
"""

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any, cast

import orjson

FRAME_SEPARATOR = b"\n\n"


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
    """Take every complete frame out of the buffer, leaving any partial tail behind."""
    while FRAME_SEPARATOR in buffer:
        frame, _, remainder = bytes(buffer).partition(FRAME_SEPARATOR)
        buffer.clear()
        buffer.extend(remainder)
        yield frame


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
