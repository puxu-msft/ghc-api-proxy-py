from collections.abc import AsyncIterator


class BufferLimitExceeded(MemoryError):
    pass


async def collect_with_limit(
    stream: AsyncIterator[bytes],
    *,
    cap_bytes: int,
) -> bytes:
    buffer = bytearray()
    async for chunk in stream:
        buffer.extend(chunk)
        if len(buffer) > cap_bytes:
            raise BufferLimitExceeded(f"stream buffer exceeded {cap_bytes} bytes")
    return bytes(buffer)