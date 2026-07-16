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
        text_value = self._buffer
        prefix = [0] * len(text_value)
        for index in range(1, len(text_value)):
            matched = prefix[index - 1]
            while matched > 0 and text_value[index] != text_value[matched]:
                matched = prefix[matched - 1]
            if text_value[index] == text_value[matched]:
                matched += 1
            prefix[index] = matched
        if not prefix:
            return None
        pattern_length = len(text_value) - prefix[-1]
        if pattern_length < self._min_length or len(text_value) % pattern_length:
            return None
        repetitions = len(text_value) // pattern_length
        if repetitions >= self._min_repetitions:
            return RepetitionResult(text_value[:pattern_length], repetitions)
        return None