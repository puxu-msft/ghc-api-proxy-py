from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RepetitionResult:
    pattern: str
    repetitions: int


class RepetitionDetector:
    def __init__(
        self,
        *,
        min_pattern_length: int = 50,
        min_repetitions: int = 3,
        buffer_size: int = 10_000,
    ) -> None:
        self._min_length = min_pattern_length
        self._min_repetitions = min_repetitions
        self._buffer_size = buffer_size
        self._buffer = ""

    def feed(self, text: str) -> RepetitionResult | None:
        self._buffer = (self._buffer + text)[-self._buffer_size :]
        size = len(self._buffer)
        for pattern_length in range(self._min_length, size // self._min_repetitions + 1):
            pattern = self._buffer[-pattern_length:]
            repetitions = 0
            cursor = size
            while (
                cursor >= pattern_length
                and self._buffer[cursor - pattern_length : cursor] == pattern
            ):
                repetitions += 1
                cursor -= pattern_length
            if repetitions >= self._min_repetitions:
                return RepetitionResult(pattern, repetitions)
        return None