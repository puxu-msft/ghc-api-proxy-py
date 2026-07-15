import copy
from typing import Any


class ChatStreamAccumulator:
    def __init__(self) -> None:
        self._content: list[str] = []
        self._id: str | None = None
        self._model: str | None = None
        self._finish_reason: str | None = None
        self._usage: dict[str, Any] = {}

    def process(self, event: dict[str, Any]) -> None:
        self._id = event.get("id", self._id)
        self._model = event.get("model", self._model)
        choices = event.get("choices", [])
        if choices:
            choice = choices[0]
            delta = choice.get("delta", {})
            if isinstance(delta.get("content"), str):
                self._content.append(delta["content"])
            self._finish_reason = choice.get("finish_reason") or self._finish_reason
        if isinstance(event.get("usage"), dict):
            self._usage = copy.deepcopy(event["usage"])

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self._id,
            "model": self._model,
            "content": "".join(self._content),
            "finish_reason": self._finish_reason,
            "usage": copy.deepcopy(self._usage),
        }