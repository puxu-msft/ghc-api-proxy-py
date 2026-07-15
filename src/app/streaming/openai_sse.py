from collections.abc import AsyncIterator

from app.wire_json import JsonValue, loads


async def parse_sse_json(stream: AsyncIterator[bytes]) -> AsyncIterator[JsonValue]:
    buffer = bytearray()
    async for chunk in stream:
        buffer.extend(chunk.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
        while b"\n\n" in buffer:
            frame, _, remainder = buffer.partition(b"\n\n")
            buffer = bytearray(remainder)
            data_lines = [line[6:] for line in frame.splitlines() if line.startswith(b"data: ")]
            if not data_lines:
                continue
            data = b"\n".join(data_lines)
            if data == b"[DONE]":
                return
            yield loads(data)