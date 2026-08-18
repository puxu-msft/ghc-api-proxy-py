import copy
from typing import Any


class ResponsesStreamAccumulator:
    def __init__(self) -> None:
        self._text: list[str] = []
        self._response: dict[str, Any] = {}
        self._usage: dict[str, Any] = {}

    def process(self, event: dict[str, Any]) -> None:
        if event.get("type") == "response.output_text.delta" and isinstance(
            event.get("delta"), str
        ):
            self._text.append(event["delta"])
        if isinstance(event.get("response"), dict):
            self._response = copy.deepcopy(event["response"])
            if isinstance(self._response.get("usage"), dict):
                self._usage = copy.deepcopy(self._response["usage"])

    def snapshot(self) -> dict[str, Any]:
        return {
            "output_text": "".join(self._text),
            "response": copy.deepcopy(self._response),
            "usage": copy.deepcopy(self._usage),
        }
