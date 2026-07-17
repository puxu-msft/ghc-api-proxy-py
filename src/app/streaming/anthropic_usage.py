from typing import Any, cast

from app.wire_json import loads


class AnthropicSSEUsageTap:
    """Incrementally observes Anthropic SSE usage without changing wire chunks."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._usage: dict[str, int] = {}

    def feed(self, chunk: bytes) -> None:
        self._buffer.extend(chunk.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
        while b"\n\n" in self._buffer:
            frame, _, remainder = self._buffer.partition(b"\n\n")
            self._buffer = bytearray(remainder)
            data_lines = [
                line[6:]
                for line in frame.splitlines()
                if line.startswith(b"data: ")
            ]
            if not data_lines:
                continue
            try:
                value = loads(b"\n".join(data_lines))
            except ValueError:
                continue
            if not isinstance(value, dict):
                continue
            event = cast(dict[str, Any], value)
            usage: object = event.get("usage")
            if event.get("type") == "message_start" and isinstance(
                event.get("message"), dict
            ):
                usage = cast(dict[str, Any], event["message"]).get("usage")
            if not isinstance(usage, dict):
                continue
            for key, raw_value in cast(dict[str, Any], usage).items():
                if isinstance(raw_value, int) and raw_value >= 0:
                    self._usage[key] = raw_value

    @property
    def usage(self) -> dict[str, int]:
        return dict(self._usage)
