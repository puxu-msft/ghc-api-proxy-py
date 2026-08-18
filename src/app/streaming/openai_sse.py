from collections.abc import AsyncIterator

from app.wire_json import JsonValue, loads


async def parse_sse_json(stream: AsyncIterator[bytes]) -> AsyncIterator[JsonValue]:
    buffer = bytearray()
    frame_lines: list[bytes] = []
    async for chunk in stream:
        buffer.extend(chunk)
        while (line := _pop_sse_line(buffer)) is not None:
            if line:
                frame_lines.append(line)
                continue
            data = b"\n".join(
                value
                for line_value in frame_lines
                if (value := _data_field_value(line_value)) is not None
            )
            frame_lines.clear()
            if not data:
                continue
            if data == b"[DONE]":
                return
            yield loads(data)


def _pop_sse_line(buffer: bytearray) -> bytes | None:
    for index, value in enumerate(buffer):
        if value == 10:
            line = bytes(buffer[:index])
            del buffer[: index + 1]
            return line
        if value == 13:
            if index + 1 == len(buffer):
                return None
            line = bytes(buffer[:index])
            consumed = index + 2 if buffer[index + 1] == 10 else index + 1
            del buffer[:consumed]
            return line
    return None


def _data_field_value(line: bytes) -> bytes | None:
    if not line.startswith(b"data:"):
        return None
    value = line[5:]
    return value[1:] if value.startswith(b" ") else value
