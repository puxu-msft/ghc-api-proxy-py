"""One SSE frame, in whichever protocol wrote it.

The wire envelope is the same for both client legs — `event: <name>` then `data: <json>` then a blank line — so it lives here rather than inside either format's module.
It used to sit in the Anthropic one, which made the Responses framer import from it for a type that has nothing to do with Anthropic, and made one of two equal formats look like the base the other derived from.

The reading half of the same layer is `sse_source`.
"""

from dataclasses import dataclass
from typing import Any

import orjson


@dataclass(frozen=True, slots=True)
class SseFrame:
    event: str
    data: dict[str, Any]

    def encode(self) -> bytes:
        body = orjson.dumps(self.data).decode()
        return f"event: {self.event}\ndata: {body}\n\n".encode()
